// Package server wires the proxy's HTTP surface: routing, authentication,
// permission checks and forwarding to the upstream PowerDNS API.
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	swaggerFiles "github.com/swaggo/files/v2"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
	"github.com/akquinet/powerdns-api-proxy/internal/metrics"
	"github.com/akquinet/powerdns-api-proxy/internal/middleware"
	"github.com/akquinet/powerdns-api-proxy/internal/upstream"
	"github.com/akquinet/powerdns-api-proxy/internal/utils"
)

// App holds the dependencies shared by all handlers.
type App struct {
	Cfg                *config.Config
	Conn               *upstream.Connector
	Metrics            *metrics.Metrics
	MetricsRequireAuth bool
	AuditEnabled       bool
	AuditLogClientIP   bool
	ForwardedAllowIPs  string
	// PanicReporter is called with recovered panic values, if set. Wire it to
	// your error tracker (e.g. Sentry) in main.
	PanicReporter func(r *http.Request, recovered any)
}

type contextKey int

const environmentKey contextKey = iota

// envFrom returns the authenticated environment stored by auth.
func envFrom(r *http.Request) *config.Environment {
	env, _ := r.Context().Value(environmentKey).(*config.Environment)
	return env
}

// Handler builds the middleware chain and router.
func (a *App) Handler() http.Handler {
	return a.router()
}

func (a *App) router() *chi.Mux {
	r := chi.NewRouter()

	// Outermost first.
	r.Use(a.recoverer)
	r.Use(middleware.ProxyHeaders(a.ForwardedAllowIPs))
	r.Use(middleware.AccessLog())
	r.Use(middleware.NewAudit(a.Cfg, a.AuditEnabled, a.AuditLogClientIP).Wrap)
	if a.Metrics != nil {
		r.Use(a.Metrics.Middleware(a.Cfg))
	}

	r.Get("/", a.handleIndex)
	r.Head("/", a.handleIndex)
	if a.Cfg.APIDocsEnabled {
		r.Get("/docs", a.handleDocsIndex)
		r.Get("/docs/", a.handleDocsIndex)
		r.Get("/docs/openapi.json", a.handleOpenAPI)
		r.Handle("/docs/*", http.StripPrefix("/docs/", http.FileServerFS(swaggerFiles.FS)))
	}
	r.Get("/health/pdns", a.handleHealth)
	if a.Metrics != nil {
		r.Get("/metrics", a.metricsHandler().ServeHTTP)
	}

	r.Group(func(r chi.Router) {
		r.Use(a.auth)
		r.Get("/info/allowed", a.handleAllowed)
		r.Get("/info/zone-allowed", a.handleZoneAllowed)
		r.Get("/api", a.handleAPIRoot)
	})

	// Every PowerDNS route runs behind auth and path-parameter validation.
	// The guard is applied per route via With because chi group middleware
	// runs before route matching, where path parameters are not yet decoded.
	// TestRouteCoverage asserts that every /api/v1 endpoint in the router
	// comes from apiV1Routes and carries both middlewares.
	r.Route("/api/v1", func(r chi.Router) {
		r.Use(a.auth)
		for _, rt := range a.apiV1Routes() {
			r.With(a.guardPathParams).Method(rt.method, rt.pattern, rt.handler)
		}
	})

	return r
}

// apiRoute is one PowerDNS API endpoint, relative to /api/v1.
type apiRoute struct {
	method  string
	pattern string
	handler http.HandlerFunc
}

// apiV1Routes lists every PowerDNS endpoint. Register routes here, not
// directly on the router, so TestRouteCoverage keeps its guarantees.
func (a *App) apiV1Routes() []apiRoute {
	return []apiRoute{
		{http.MethodGet, "/servers", a.handleGetServers},
		{http.MethodGet, "/servers/{server_id}", a.handleGetServer},
		{http.MethodGet, "/servers/{server_id}/config", a.handleGetConfig},
		{http.MethodGet, "/servers/{server_id}/config/{config_setting_name}", a.handleGetConfigSetting},
		{http.MethodGet, "/servers/{server_id}/statistics", a.handleGetStatistics},
		{http.MethodGet, "/servers/{server_id}/search-data", a.handleSearchData},
		{http.MethodGet, "/servers/{server_id}/zones", a.handleGetZones},
		{http.MethodPost, "/servers/{server_id}/zones", a.handleCreateZone},
		{http.MethodGet, "/servers/{server_id}/zones/{zone_id}", a.handleGetZone},
		{http.MethodPut, "/servers/{server_id}/zones/{zone_id}", a.handlePutZone},
		{http.MethodPatch, "/servers/{server_id}/zones/{zone_id}", a.handlePatchZone},
		{http.MethodDelete, "/servers/{server_id}/zones/{zone_id}", a.handleDeleteZone},
		{http.MethodPut, "/servers/{server_id}/zones/{zone_id}/notify", a.handleNotify},
		{http.MethodPut, "/servers/{server_id}/zones/{zone_id}/rectify", a.handleRectify},

		{http.MethodGet, "/servers/{server_id}/zones/{zone_id}/cryptokeys", a.handleKeyed(cryptokeysResource, false, false)},
		{http.MethodPost, "/servers/{server_id}/zones/{zone_id}/cryptokeys", a.handleKeyed(cryptokeysResource, false, true)},
		{http.MethodGet, "/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}", a.handleKeyed(cryptokeysResource, true, false)},
		{http.MethodPut, "/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}", a.handleKeyed(cryptokeysResource, true, true)},
		{http.MethodDelete, "/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}", a.handleKeyed(cryptokeysResource, true, false)},

		{http.MethodGet, "/servers/{server_id}/tsigkeys", a.handleKeyed(tsigkeysResource, false, false)},
		{http.MethodPost, "/servers/{server_id}/tsigkeys", a.handleKeyed(tsigkeysResource, false, true)},
		{http.MethodGet, "/servers/{server_id}/tsigkeys/{tsigkey_id}", a.handleKeyed(tsigkeysResource, true, false)},
		{http.MethodPut, "/servers/{server_id}/tsigkeys/{tsigkey_id}", a.handleKeyed(tsigkeysResource, true, true)},
		{http.MethodDelete, "/servers/{server_id}/tsigkeys/{tsigkey_id}", a.handleKeyed(tsigkeysResource, true, false)},
	}
}

// auth authenticates the token and stores the environment in the context.
func (a *App) auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := r.Header.Get("X-API-Key")
		if token == "" {
			writeError(w, httperr.New(http.StatusUnprocessableEntity, "Missing X-API-Key header"))
			return
		}
		env := a.Cfg.EnvironmentForToken(token)
		if env == nil {
			writeError(w, httperr.NotAuthorized())
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), environmentKey, env)))
	})
}

// pathParamNames lists every path parameter that is forwarded into an upstream
// URL. validatePathParams rejects values outside the allowlist, so a new route
// with a new parameter must add it here; TestRouteCoverage enforces that.
var pathParamNames = []string{"server_id", "config_setting_name", "zone_id", "cryptokey_id", "tsigkey_id"}

// guardPathParams validates path parameters before any PowerDNS handler runs.
func (a *App) guardPathParams(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for _, name := range pathParamNames {
			value := chi.URLParam(r, name)
			if value == "" {
				continue
			}
			if !utils.CheckPathParamSafe(value) {
				logging.Log.Warn("Rejected path parameter", "name", name, "value", value)
				writeError(w, httperr.InvalidPathParam(name))
				return
			}
		}
		if serverID := chi.URLParam(r, "server_id"); serverID != "" && serverID != "localhost" {
			writeError(w, httperr.ServerNotFound())
			return
		}
		next.ServeHTTP(w, r)
	})
}

// forward proxies a request to the upstream and streams the reply.
func (a *App) forward(w http.ResponseWriter, r *http.Request, method, path string, query url.Values, body []byte) {
	resp, err := a.Conn.Request(r.Context(), method, path, query, body)
	if err != nil {
		logging.Log.Error("Error connecting to upstream PowerDNS API", "error", err.Error())
		writeError(w, httperr.Upstream(""))
		return
	}
	if resp.IsSuccess() {
		writeUpstream(w, resp)
		return
	}
	writeError(w, mapUpstream(resp))
}

func readBody(r *http.Request) []byte {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return nil
	}
	return body
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func zoneUpstreamPath(serverID, zoneID string) string {
	return fmt.Sprintf("/api/v1/servers/%s/zones/%s", serverID, zoneID)
}

// recoverer converts unexpected panics into PowerDNS error responses and
// forwards them to the optional PanicReporter (e.g. Sentry).
func (a *App) recoverer(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				logging.Log.Error("Unhandled exception during request processing", "panic", fmt.Sprint(rec))
				if a.PanicReporter != nil {
					a.PanicReporter(r, rec)
				}
				writeError(w, httperr.Unhandled(""))
			}
		}()
		next.ServeHTTP(w, r)
	})
}

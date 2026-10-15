// Package server wires the proxy's HTTP surface: routing, authentication,
// permission checks and forwarding to the upstream PowerDNS API.
package server

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"

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

	// routes records the registered patterns and which wrapper guards them.
	// It exists so tests can assert authentication and path-parameter
	// validation cover every route, even ones added later.
	routes []routeEntry
}

type routeEntry struct {
	pattern string
	// wrapper is "env" (token auth), "pdns" (env + path-param validation) or
	// "plain" (no auth).
	wrapper string
}

// envHandler is a handler that has already passed authentication.
type envHandler func(w http.ResponseWriter, r *http.Request, env *config.Environment)

// Handler builds the full middleware chain around the router.
func (a *App) Handler() http.Handler {
	h := a.router()

	if a.Metrics != nil {
		h = a.Metrics.Middleware(a.Cfg, h)
	}
	h = middleware.NewAudit(a.Cfg, a.AuditEnabled, a.AuditLogClientIP).Wrap(h)
	h = middleware.NewAccessLog(h)
	h = middleware.NewProxyHeaders(a.ForwardedAllowIPs, h)
	return a.recoverPanic(h)
}

func (a *App) router() http.Handler {
	mux := http.NewServeMux()
	a.routes = nil

	// handle registers a pattern and records which wrapper guards it. All
	// route registration must go through here so the route safety net test can
	// assert coverage.
	var handle func(pattern, wrapper string, h http.HandlerFunc)
	handle = func(pattern, wrapper string, h http.HandlerFunc) {
		a.routes = append(a.routes, routeEntry{pattern: pattern, wrapper: wrapper})
		mux.HandleFunc(pattern, h)
	}

	handle("GET /{$}", "plain", a.handleIndex)
	handle("HEAD /{$}", "plain", a.handleIndex)
	if a.Cfg.APIDocsEnabled {
		handle("GET /docs", "plain", a.handleDocs)
		handle("GET /docs/{path...}", "plain", a.handleDocs)
	}
	handle("GET /health/pdns", "plain", a.handleHealth)
	if a.Metrics != nil {
		a.routes = append(a.routes, routeEntry{pattern: "GET /metrics", wrapper: "plain"})
		mux.Handle("GET /metrics", a.metricsHandler())
	}

	handle("GET /info/allowed", "env", a.withEnv(a.handleAllowed))
	handle("GET /info/zone-allowed", "env", a.withEnv(a.handleZoneAllowed))
	handle("GET /api", "env", a.withEnv(a.handleAPIRoot))

	handle("GET /api/v1/servers", "pdns", a.withPDNS(a.handleGetServers))
	handle("GET /api/v1/servers/{server_id}", "pdns", a.withPDNS(a.handleGetServer))
	handle("GET /api/v1/servers/{server_id}/config", "pdns", a.withPDNS(a.handleGetConfig))
	handle("GET /api/v1/servers/{server_id}/config/{config_setting_name}", "pdns", a.withPDNS(a.handleGetConfigSetting))
	handle("GET /api/v1/servers/{server_id}/statistics", "pdns", a.withPDNS(a.handleGetStatistics))
	handle("GET /api/v1/servers/{server_id}/zones", "pdns", a.withPDNS(a.handleGetZones))
	handle("POST /api/v1/servers/{server_id}/zones", "pdns", a.withPDNS(a.handleCreateZone))
	handle("GET /api/v1/servers/{server_id}/zones/{zone_id}", "pdns", a.withPDNS(a.handleGetZone))
	handle("PUT /api/v1/servers/{server_id}/zones/{zone_id}", "pdns", a.withPDNS(a.handlePutZone))
	handle("PATCH /api/v1/servers/{server_id}/zones/{zone_id}", "pdns", a.withPDNS(a.handlePatchZone))
	handle("DELETE /api/v1/servers/{server_id}/zones/{zone_id}", "pdns", a.withPDNS(a.handleDeleteZone))
	handle("PUT /api/v1/servers/{server_id}/zones/{zone_id}/notify", "pdns", a.withPDNS(a.handleNotify))
	handle("PUT /api/v1/servers/{server_id}/zones/{zone_id}/rectify", "pdns", a.withPDNS(a.handleRectify))
	handle("GET /api/v1/servers/{server_id}/search-data", "pdns", a.withPDNS(a.handleSearchData))

	handle("GET /api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys", "pdns", a.withPDNS(a.handleKeyed(cryptokeysResource, false, false)))
	handle("POST /api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys", "pdns", a.withPDNS(a.handleKeyed(cryptokeysResource, false, true)))
	handle("GET /api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}", "pdns", a.withPDNS(a.handleKeyed(cryptokeysResource, true, false)))
	handle("PUT /api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}", "pdns", a.withPDNS(a.handleKeyed(cryptokeysResource, true, true)))
	handle("DELETE /api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}", "pdns", a.withPDNS(a.handleKeyed(cryptokeysResource, true, false)))

	handle("GET /api/v1/servers/{server_id}/tsigkeys", "pdns", a.withPDNS(a.handleKeyed(tsigkeysResource, false, false)))
	handle("POST /api/v1/servers/{server_id}/tsigkeys", "pdns", a.withPDNS(a.handleKeyed(tsigkeysResource, false, true)))
	handle("GET /api/v1/servers/{server_id}/tsigkeys/{tsigkey_id}", "pdns", a.withPDNS(a.handleKeyed(tsigkeysResource, true, false)))
	handle("PUT /api/v1/servers/{server_id}/tsigkeys/{tsigkey_id}", "pdns", a.withPDNS(a.handleKeyed(tsigkeysResource, true, true)))
	handle("DELETE /api/v1/servers/{server_id}/tsigkeys/{tsigkey_id}", "pdns", a.withPDNS(a.handleKeyed(tsigkeysResource, true, false)))

	return mux
}

// withEnv authenticates the token and injects the environment.
func (a *App) withEnv(h envHandler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
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
		h(w, r, env)
	}
}

// withPDNS authenticates and validates path parameters before the handler runs.
func (a *App) withPDNS(h envHandler) http.HandlerFunc {
	return a.withEnv(func(w http.ResponseWriter, r *http.Request, env *config.Environment) {
		if err := validatePathParams(r); err != nil {
			writeError(w, err)
			return
		}
		h(w, r, env)
	})
}

var pathParamNames = []string{"server_id", "config_setting_name", "zone_id", "cryptokey_id", "tsigkey_id"}

func validatePathParams(r *http.Request) error {
	for _, name := range pathParamNames {
		value := r.PathValue(name)
		if value == "" {
			continue
		}
		if !utils.CheckPathParamSafe(value) {
			logging.Log.Warn("Rejected path parameter", "name", name, "value", value)
			return httperr.InvalidPathParam(name)
		}
	}
	if serverID := r.PathValue("server_id"); serverID != "" && serverID != "localhost" {
		return httperr.ServerNotFound()
	}
	return nil
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

// recoverPanic converts unexpected panics into PowerDNS error responses and
// forwards them to the optional PanicReporter (e.g. Sentry).
func (a *App) recoverPanic(next http.Handler) http.Handler {
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

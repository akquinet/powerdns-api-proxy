package server

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
	"github.com/akquinet/powerdns-api-proxy/internal/perm"
)

func (a *App) handleIndex(w http.ResponseWriter, r *http.Request) {
	if !a.Cfg.IndexEnabled {
		w.WriteHeader(http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(a.Cfg.IndexHTML))
}

func (a *App) handleHealth(w http.ResponseWriter, r *http.Request) {
	logging.Log.Info("Checking upstream pdns api health")
	resp, err := a.Conn.Request(r.Context(), http.MethodGet, "/api/v1/servers", nil, nil)
	if err != nil || resp.StatusCode != http.StatusOK {
		writeJSON(w, http.StatusInternalServerError, map[string]string{
			"details": "Something is wrong :(. Please help me!",
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"details": "Upstream PowerDNS API seems to work :)",
	})
}

func (a *App) metricsHandler() http.Handler {
	h := promhttp.Handler()
	if !a.MetricsRequireAuth {
		return h
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		username, password, ok := r.BasicAuth()
		if !ok {
			w.Header().Set("WWW-Authenticate", `Basic realm="metrics"`)
			writeError(w, httperr.NotAuthorized())
			return
		}
		env := a.Cfg.EnvironmentForToken(password)
		if env == nil || env.Name != username {
			writeError(w, httperr.NotAuthorized())
			return
		}
		if !env.MetricsProxy {
			writeError(w, httperr.MetricsNotAllowed())
			return
		}
		h.ServeHTTP(w, r)
	})
}

func (a *App) handleAllowed(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"zones": envFrom(r).Zones})
}

type zoneAllowedResponse struct {
	Zone    string       `json:"zone"`
	Allowed bool         `json:"allowed"`
	Config  *config.Zone `json:"config"`
}

func (a *App) handleZoneAllowed(w http.ResponseWriter, r *http.Request) {
	env := envFrom(r)
	zone := r.URL.Query().Get("zone")
	if zone == "" {
		writeError(w, httperr.New(http.StatusUnprocessableEntity, "Missing zone parameter"))
		return
	}
	if !perm.ZoneAllowed(env, zone) {
		writeJSON(w, http.StatusOK, zoneAllowedResponse{Zone: zone, Allowed: false})
		return
	}
	zoneConfig, err := env.GetZoneIfAllowed(zone)
	if err != nil {
		writeJSON(w, http.StatusOK, zoneAllowedResponse{Zone: zone, Allowed: false})
		return
	}
	writeJSON(w, http.StatusOK, zoneAllowedResponse{Zone: zone, Allowed: true, Config: zoneConfig})
}

func (a *App) handleAPIRoot(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, []map[string]any{
		{
			"url":           "/api/v1",
			"version":       1,
			"compatibility": "PowerDNS API Proxy, PowerDNS API v1",
		},
	})
}

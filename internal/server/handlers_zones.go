package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
	"github.com/akquinet/powerdns-api-proxy/internal/perm"
)

func (a *App) handleGetServers(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	a.forward(w, r, http.MethodGet, "/api/v1/servers", nil, nil)
}

func (a *App) handleGetServer(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodGet, fmt.Sprintf("/api/v1/servers/%s", serverID), nil, nil)
}

func (a *App) handleGetConfig(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	if !perm.ConfigAllowed(env) {
		writeError(w, httperr.RessourceNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodGet, fmt.Sprintf("/api/v1/servers/%s/config", serverID), nil, nil)
}

func (a *App) handleGetConfigSetting(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	if !perm.ConfigAllowed(env) {
		writeError(w, httperr.RessourceNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	name := r.PathValue("config_setting_name")
	a.forward(w, r, http.MethodGet, fmt.Sprintf("/api/v1/servers/%s/config/%s", serverID, name), nil, nil)
}

func (a *App) handleGetStatistics(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	if !perm.StatisticsAllowed(env) {
		writeError(w, httperr.RessourceNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodGet, fmt.Sprintf("/api/v1/servers/%s/statistics", serverID), nil, nil)
}

func (a *App) handleGetZones(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	serverID := r.PathValue("server_id")
	resp, err := a.Conn.Request(r.Context(), http.MethodGet,
		fmt.Sprintf("/api/v1/servers/%s/zones", serverID), r.URL.Query(), nil)
	if err != nil {
		writeError(w, httperr.Upstream(""))
		return
	}
	if !resp.IsSuccess() {
		writeError(w, mapUpstream(resp))
		return
	}

	var rawZones []json.RawMessage
	if err := json.Unmarshal(resp.Body, &rawZones); err != nil {
		logging.Log.Error("Expected PowerDNS to return a JSON list", "body", string(resp.Body))
		writeError(w, httperr.Upstream(""))
		return
	}

	filtered := make([]json.RawMessage, 0, len(rawZones))
	for _, item := range rawZones {
		var probe struct {
			Name string `json:"name"`
		}
		if err := json.Unmarshal(item, &probe); err != nil {
			continue
		}
		if perm.ZoneAllowed(env, probe.Name) {
			filtered = append(filtered, item)
		}
	}
	writeJSON(w, resp.StatusCode, filtered)
}

func (a *App) handleCreateZone(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	body := readBody(r)
	var payload struct {
		Name string `json:"name"`
	}
	_ = json.Unmarshal(body, &payload)
	logging.Log.Info(fmt.Sprintf("Zone creation request data: %q", string(body)))

	if payload.Name == "" || !perm.ZoneAllowed(env, payload.Name) {
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	if !perm.ZoneAdmin(env, payload.Name) {
		writeError(w, httperr.ZoneAdminNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodPost, fmt.Sprintf("/api/v1/servers/%s/zones", serverID), nil, body)
}

func (a *App) handleGetZone(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	zoneID := r.PathValue("zone_id")
	if !perm.ZoneAllowed(env, zoneID) {
		logging.Log.Info("Zone not allowed", "zone", zoneID, "environment", env.Name)
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodGet, zoneUpstreamPath(serverID, zoneID), r.URL.Query(), nil)
}

func (a *App) handlePutZone(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	zoneID := r.PathValue("zone_id")
	if !perm.ZoneAllowed(env, zoneID) {
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	if !perm.ZoneAdmin(env, zoneID) {
		writeError(w, httperr.ZoneAdminNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodPut, zoneUpstreamPath(serverID, zoneID), nil, readBody(r))
}

func (a *App) handlePatchZone(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	zoneID := r.PathValue("zone_id")
	if !perm.ZoneAllowed(env, zoneID) {
		logging.Log.Info("Zone not allowed", "zone", zoneID, "environment", env.Name)
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	body := readBody(r)
	zone, err := env.GetZoneIfAllowed(zoneID)
	if err != nil {
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	var req config.RRSETRequest
	if err := json.Unmarshal(body, &req); err != nil {
		writeError(w, httperr.New(http.StatusBadRequest, "Invalid JSON body"))
		return
	}
	if err := perm.EnsureRRSetsAllowed(zone, req); err != nil {
		writeError(w, err)
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodPatch, zoneUpstreamPath(serverID, zoneID), nil, body)
}

func (a *App) handleDeleteZone(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	zoneID := r.PathValue("zone_id")
	if !perm.ZoneAdmin(env, zoneID) {
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodDelete, zoneUpstreamPath(serverID, zoneID), nil, nil)
}

func (a *App) handleNotify(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	zoneID := r.PathValue("zone_id")
	if !perm.ZoneAllowed(env, zoneID) {
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodPut, zoneUpstreamPath(serverID, zoneID)+"/notify", nil, nil)
}

func (a *App) handleRectify(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	zoneID := r.PathValue("zone_id")
	if !perm.ZoneAllowed(env, zoneID) {
		writeError(w, httperr.ZoneNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodPut, zoneUpstreamPath(serverID, zoneID)+"/rectify", nil, nil)
}

var validObjectTypes = map[string]struct{}{
	"all": {}, "zone": {}, "record": {}, "comment": {},
}

func (a *App) handleSearchData(w http.ResponseWriter, r *http.Request, env *config.Environment) {
	query := r.URL.Query()
	q := query.Get("q")
	if q == "" {
		writeError(w, httperr.New(http.StatusUnprocessableEntity, "Missing q parameter"))
		return
	}
	objectType := query.Get("object_type")
	if objectType == "" {
		objectType = "all"
	}
	if _, ok := validObjectTypes[objectType]; !ok {
		writeError(w, httperr.New(http.StatusUnprocessableEntity, "Invalid object_type"))
		return
	}

	params := url.Values{"q": {q}, "object_type": {objectType}}
	if maxStr := query.Get("max"); maxStr != "" {
		if _, err := strconv.Atoi(maxStr); err != nil {
			writeError(w, httperr.New(http.StatusUnprocessableEntity, "Invalid max parameter"))
			return
		}
		params.Set("max", maxStr)
	}

	if !perm.SearchAllowed(env, q, objectType) {
		logging.Log.Info("Search not allowed", "q", q, "object_type", objectType, "environment", env.Name)
		writeError(w, httperr.SearchNotAllowed())
		return
	}
	serverID := r.PathValue("server_id")
	a.forward(w, r, http.MethodGet,
		fmt.Sprintf("/api/v1/servers/%s/search-data", serverID), params, nil)
}

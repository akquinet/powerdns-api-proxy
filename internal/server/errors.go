package server

import (
	"encoding/json"
	"net/http"

	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
	"github.com/akquinet/powerdns-api-proxy/internal/upstream"
)

// writeError serialises an error in the PowerDNS error format.
func writeError(w http.ResponseWriter, err error) {
	apiErr := asAPIError(err)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(apiErr.Status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": apiErr.Detail})
}

func asAPIError(err error) *httperr.Error {
	if apiErr, ok := err.(*httperr.Error); ok {
		return apiErr
	}
	return httperr.Unhandled("")
}

// writeUpstream streams a successful upstream reply through unchanged.
func writeUpstream(w http.ResponseWriter, resp *upstream.Response) {
	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}
	w.Header().Set("Content-Type", contentType)
	w.WriteHeader(resp.StatusCode)
	if len(resp.Body) > 0 {
		_, _ = w.Write(resp.Body)
	}
}

// mapUpstream converts a non-2xx upstream reply to a proxy error, mirroring the
// previous status-code handling.
func mapUpstream(resp *upstream.Response) *httperr.Error {
	switch resp.StatusCode {
	case http.StatusBadRequest, http.StatusNotFound, http.StatusConflict, http.StatusUnprocessableEntity:
		detail := upstreamErrorMessage(resp)
		logging.Log.Error("PowerDNS error", "status", resp.StatusCode, "detail", detail)
		return httperr.New(resp.StatusCode, detail)
	}

	if m, ok := resp.Data.(map[string]any); ok {
		if _, has := m["error"]; has {
			detail, _ := m["error"].(string)
			logging.Log.Error("PowerDNS upstream error", "detail", detail)
			return httperr.Upstream("")
		}
	}
	logging.Log.Error("Unhandled PowerDNS error", "body", string(resp.Body))
	return httperr.Unhandled("")
}

func upstreamErrorMessage(resp *upstream.Response) string {
	switch data := resp.Data.(type) {
	case map[string]any:
		if msg, ok := data["error"].(string); ok {
			return msg
		}
		return "Unknown error"
	case string:
		return data
	default:
		if len(resp.Body) > 0 {
			return string(resp.Body)
		}
		return "Unknown error"
	}
}

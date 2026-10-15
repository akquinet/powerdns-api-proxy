// Package middleware provides the proxy's HTTP middleware: audit logging,
// access logging and trusted reverse-proxy header handling.
package middleware

import (
	"bytes"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"strings"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
)

const unauthenticated = "UNAUTHENTICATED"

// Audit logs every /api/v1 request, including forbidden and unauthenticated
// attempts. It is a no-op for other paths or when disabled.
type Audit struct {
	cfg         *config.Config
	enabled     bool
	logClientIP bool
}

// NewAudit builds an audit middleware.
func NewAudit(cfg *config.Config, enabled, logClientIP bool) *Audit {
	return &Audit{cfg: cfg, enabled: enabled, logClientIP: logClientIP}
}

// Wrap returns next wrapped with audit logging.
func (m *Audit) Wrap(next http.Handler) http.Handler {
	if !m.enabled {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/v1/") {
			next.ServeHTTP(w, r)
			return
		}

		environmentName := unauthenticated
		if env := m.cfg.EnvironmentForToken(r.Header.Get("X-API-Key")); env != nil {
			environmentName = env.Name
		}

		var payload any
		if r.Method == http.MethodPost || r.Method == http.MethodPut || r.Method == http.MethodPatch {
			if body, err := io.ReadAll(r.Body); err == nil {
				r.Body = io.NopCloser(bytes.NewReader(body))
				if len(body) > 0 {
					payload = decodeJSON(body)
				}
			}
		}

		var queryParams map[string]string
		if q := r.URL.Query(); len(q) > 0 {
			queryParams = make(map[string]string, len(q))
			for key := range q {
				queryParams[key] = q.Get(key)
			}
		}

		clientIP := ""
		if m.logClientIP {
			if host := remoteHost(r.RemoteAddr); host != "" {
				clientIP = host
			} else {
				clientIP = "unknown"
			}
		}

		rec := NewResponseRecorder(w)
		next.ServeHTTP(rec, r)

		path := strings.ReplaceAll(r.URL.Path, "/api/v1/servers/localhost", "")
		logging.Log.Audit(environmentName, r.Method, path, rec.Status, payload, queryParams, clientIP)
	})
}

// decodeJSON parses b, returning nil for anything that is not valid JSON.
func decodeJSON(b []byte) any {
	var v any
	if err := json.Unmarshal(b, &v); err != nil {
		return nil
	}
	return v
}

// remoteHost returns the host part of a "host:port" remote address.
func remoteHost(addr string) string {
	if addr == "" {
		return ""
	}
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		return addr
	}
	return host
}

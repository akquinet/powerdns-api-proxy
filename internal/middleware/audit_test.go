package middleware

import (
	"bytes"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
)

const auditToken = "lashflkashlfgkashglashglashgl"

func auditConfig(t *testing.T) *config.Config {
	t.Helper()
	yaml := fmt.Sprintf(`
pdns_api_url: "https://pdns.example"
pdns_api_token: "upstream"
environments:
  - name: "Test 1"
    token_sha512: %q
`, config.HashToken(auditToken))
	cfg, err := config.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	return cfg
}

func captureLogs(t *testing.T) *bytes.Buffer {
	t.Helper()
	buf := &bytes.Buffer{}
	original := logging.Log
	logging.Log = logging.New(logging.LevelInfo, "text")
	logging.Log.SetOutput(buf)
	t.Cleanup(func() { logging.Log = original })
	return buf
}

func TestAuditLogsAuthenticatedRequest(t *testing.T) {
	buf := captureLogs(t)
	cfg := auditConfig(t)

	handler := NewAudit(cfg, true, false).Wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))

	req := httptest.NewRequest(http.MethodPatch, "/api/v1/servers/localhost/zones/example.com.",
		strings.NewReader(`{"rrsets":[]}`))
	req.Header.Set("X-API-Key", auditToken)
	handler.ServeHTTP(httptest.NewRecorder(), req)

	line := buf.String()
	if !strings.Contains(line, "AUDIT: Test 1 PATCH /zones/example.com. 204") {
		t.Errorf("unexpected audit line: %s", line)
	}
	if strings.Contains(line, "/api/v1/servers/localhost") {
		t.Errorf("server prefix must be stripped: %s", line)
	}
}

func TestAuditLogsUnauthenticatedRequest(t *testing.T) {
	buf := captureLogs(t)
	cfg := auditConfig(t)

	handler := NewAudit(cfg, true, false).Wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	req := httptest.NewRequest(http.MethodGet, "/api/v1/servers/localhost/zones", nil)
	handler.ServeHTTP(httptest.NewRecorder(), req)

	if !strings.Contains(buf.String(), "AUDIT: UNAUTHENTICATED GET /zones 401") {
		t.Errorf("unexpected audit line: %s", buf.String())
	}
}

func TestAuditSkipsNonAPIPaths(t *testing.T) {
	buf := captureLogs(t)
	cfg := auditConfig(t)
	handler := NewAudit(cfg, true, false).Wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/health/pdns", nil)
	handler.ServeHTTP(httptest.NewRecorder(), req)
	if buf.Len() != 0 {
		t.Errorf("expected no audit output, got: %s", buf.String())
	}
}

func TestAuditDisabled(t *testing.T) {
	buf := captureLogs(t)
	cfg := auditConfig(t)
	handler := NewAudit(cfg, false, false).Wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/api/v1/servers/localhost/zones", nil)
	handler.ServeHTTP(httptest.NewRecorder(), req)
	if buf.Len() != 0 {
		t.Errorf("expected no audit output when disabled, got: %s", buf.String())
	}
}

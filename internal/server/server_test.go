package server

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/upstream"
)

const testToken = "lashflkashlfgkashglashglashgl"

type mockUpstream struct {
	mu      sync.Mutex
	calls   []string
	respond func(w http.ResponseWriter, r *http.Request)
}

func (m *mockUpstream) serve(w http.ResponseWriter, r *http.Request) {
	m.mu.Lock()
	m.calls = append(m.calls, r.Method+" "+r.URL.Path)
	m.mu.Unlock()
	if m.respond != nil {
		m.respond(w, r)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func (m *mockUpstream) callCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.calls)
}

func newTestServer(t *testing.T, mock *mockUpstream) (*httptest.Server, *config.Config) {
	t.Helper()
	up := httptest.NewServer(http.HandlerFunc(mock.serve))
	t.Cleanup(up.Close)

	yaml := fmt.Sprintf(`
pdns_api_url: %q
pdns_api_token: "upstream"
metrics_enabled: false
environments:
  - name: "Test 1"
    token_sha512: %q
    zones:
      - name: "test.example.com."
        records: ["test.example.com."]
`, up.URL, config.HashToken(testToken))

	cfg, err := config.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse config: %v", err)
	}

	app := &App{
		Cfg:               cfg,
		Conn:              upstream.New(cfg.PDNSAPIURL, cfg.PDNSAPIToken, cfg.PDNSAPIVerifySSL),
		ForwardedAllowIPs: "127.0.0.1",
	}
	srv := httptest.NewServer(app.Handler())
	t.Cleanup(srv.Close)
	return srv, cfg
}

func do(t *testing.T, srv *httptest.Server, method, path, token, body string) *http.Response {
	t.Helper()
	var reader io.Reader
	if body != "" {
		reader = strings.NewReader(body)
	}
	req, err := http.NewRequest(method, srv.URL+path, reader)
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	if token != "" {
		req.Header.Set("X-API-Key", token)
	}
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := srv.Client().Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	return resp
}

func decodeError(t *testing.T, resp *http.Response) string {
	t.Helper()
	var payload struct {
		Error string `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		t.Fatalf("decode error body: %v", err)
	}
	return payload.Error
}

func TestMissingTokenReturns422(t *testing.T) {
	srv, _ := newTestServer(t, &mockUpstream{})
	resp := do(t, srv, http.MethodGet, "/info/allowed", "", "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnprocessableEntity {
		t.Errorf("status = %d, want 422", resp.StatusCode)
	}
}

func TestWrongTokenReturns401(t *testing.T) {
	srv, _ := newTestServer(t, &mockUpstream{})
	resp := do(t, srv, http.MethodGet, "/info/allowed", "wrong", "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", resp.StatusCode)
	}
	if body := decodeError(t, resp); body != "Unauthorized" {
		t.Errorf("error = %q, want Unauthorized", body)
	}
}

func TestAllowedListsZones(t *testing.T) {
	srv, _ := newTestServer(t, &mockUpstream{})
	resp := do(t, srv, http.MethodGet, "/info/allowed", testToken, "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var payload struct {
		Zones []struct {
			Name string `json:"name"`
		} `json:"zones"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(payload.Zones) != 1 || payload.Zones[0].Name != "test.example.com." {
		t.Errorf("unexpected zones: %+v", payload.Zones)
	}
}

func TestZonesListFiltered(t *testing.T) {
	mock := &mockUpstream{respond: func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[{"name":"test.example.com."},{"name":"other.example.com."}]`))
	}}
	srv, _ := newTestServer(t, mock)
	resp := do(t, srv, http.MethodGet, "/api/v1/servers/localhost/zones", testToken, "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var zones []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&zones); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(zones) != 1 || zones[0]["name"] != "test.example.com." {
		t.Errorf("expected filtering, got %+v", zones)
	}
}

func TestPathParamInjectionRejected(t *testing.T) {
	mock := &mockUpstream{}
	srv, _ := newTestServer(t, mock)
	for _, zoneID := range []string{"other.org.%3F.example.com.", "other.org.%23.example.com."} {
		resp := do(t, srv, http.MethodGet, "/api/v1/servers/localhost/zones/"+zoneID, testToken, "")
		if resp.StatusCode != http.StatusBadRequest {
			t.Errorf("zone %q: status = %d, want 400", zoneID, resp.StatusCode)
		}
		resp.Body.Close()
	}
	if mock.callCount() != 0 {
		t.Errorf("upstream should not be called, got %d calls", mock.callCount())
	}
}

func TestUnknownServerIDReturns404(t *testing.T) {
	mock := &mockUpstream{}
	srv, _ := newTestServer(t, mock)
	resp := do(t, srv, http.MethodGet, "/api/v1/servers/other/zones", testToken, "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Errorf("status = %d, want 404", resp.StatusCode)
	}
	if mock.callCount() != 0 {
		t.Error("upstream should not be called")
	}
}

func TestPatchDeniedRRSet(t *testing.T) {
	mock := &mockUpstream{}
	srv, _ := newTestServer(t, mock)
	body := `{"rrsets":[{"name":"www.example.com.","type":"A","changetype":"REPLACE","ttl":60,"records":[]}]}`
	resp := do(t, srv, http.MethodPatch, "/api/v1/servers/localhost/zones/test.example.com.", testToken, body)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status = %d, want 403", resp.StatusCode)
	}
	if mock.callCount() != 0 {
		t.Error("upstream should not be called for denied rrset")
	}
}

func TestPatchAllowedRRSetForwarded(t *testing.T) {
	mock := &mockUpstream{respond: func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}}
	srv, _ := newTestServer(t, mock)
	body := `{"rrsets":[{"name":"test.example.com.","type":"A","changetype":"REPLACE","ttl":60,"records":[]}]}`
	resp := do(t, srv, http.MethodPatch, "/api/v1/servers/localhost/zones/test.example.com.", testToken, body)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNoContent {
		t.Fatalf("status = %d, want 204", resp.StatusCode)
	}
	if mock.callCount() != 1 {
		t.Errorf("expected one upstream call, got %d", mock.callCount())
	}
}

func TestDeleteWithoutAdminDenied(t *testing.T) {
	mock := &mockUpstream{}
	srv, _ := newTestServer(t, mock)
	resp := do(t, srv, http.MethodDelete, "/api/v1/servers/localhost/zones/test.example.com.", testToken, "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Errorf("status = %d, want 403", resp.StatusCode)
	}
	if mock.callCount() != 0 {
		t.Error("upstream should not be called")
	}
}

func TestUpstreamErrorPassthrough(t *testing.T) {
	mock := &mockUpstream{respond: func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"Could not find domain"}`))
	}}
	srv, _ := newTestServer(t, mock)
	resp := do(t, srv, http.MethodGet, "/api/v1/servers/localhost/zones/test.example.com.", testToken, "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", resp.StatusCode)
	}
	if body := decodeError(t, resp); body != "Could not find domain" {
		t.Errorf("error = %q", body)
	}
}

func TestIndexServed(t *testing.T) {
	srv, _ := newTestServer(t, &mockUpstream{})
	resp := do(t, srv, http.MethodGet, "/", "", "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "PowerDNS API Proxy") {
		t.Error("index body missing title")
	}
}

func TestAPIRootRequiresToken(t *testing.T) {
	srv, _ := newTestServer(t, &mockUpstream{})
	resp := do(t, srv, http.MethodGet, "/api", "", "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnprocessableEntity {
		t.Errorf("status = %d, want 422", resp.StatusCode)
	}
}

func TestGracefulMetricsRouteAbsentWhenDisabled(t *testing.T) {
	srv, _ := newTestServer(t, &mockUpstream{})
	resp := do(t, srv, http.MethodGet, "/metrics", "", "")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Errorf("status = %d, want 404 when metrics disabled", resp.StatusCode)
	}
}

package metrics

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
)

func TestMetricsSeriesRegisteredAndRecorded(t *testing.T) {
	reg := prometheus.NewRegistry()
	m := New(reg)

	yaml := fmt.Sprintf(`
pdns_api_url: "https://pdns.example"
pdns_api_token: "upstream"
environments:
  - name: "Test 1"
    token_sha512: %q
`, config.HashToken("lashflkashlfgkashglashglashgl"))
	cfg, err := config.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}

	handler := m.Middleware(cfg)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/servers", nil)
	req.Header.Set("X-API-Key", "lashflkashlfgkashglashglashgl")
	handler.ServeHTTP(httptest.NewRecorder(), req)

	families, err := reg.Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	names := map[string]bool{}
	for _, f := range families {
		names[f.GetName()] = true
	}
	for _, want := range []string{
		"http_requests_total",
		"http_request_size_bytes",
		"http_response_size_bytes",
		"http_request_duration_highr_seconds",
		"http_request_duration_seconds",
		"http_requests_environment",
	} {
		if !names[want] {
			t.Errorf("metric %q not registered", want)
		}
	}
}

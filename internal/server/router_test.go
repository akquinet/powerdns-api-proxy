package server

import (
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/upstream"
)

// TestRouteCoverage guards the two conventions every route must follow:
//
//   - every path parameter is known to validatePathParams, so unknown
//     parameters can never skip the injection check;
//   - every /api/v1 route goes through withPDNS, so token authentication and
//     path-parameter validation cannot be forgotten for a new route.
//
// Adding a route provides no protection on its own: update the expectation
// here instead of connecting a new handler directly to the mux.
func TestRouteCoverage(t *testing.T) {
	up := "http://pdns.example"
	app := &App{
		Cfg: &config.Config{
			PDNSAPIURL:     up,
			APIDocsEnabled: true,
		},
		Conn: upstream.New(up, "token", true),
	}
	_ = app.router()

	if len(app.routes) == 0 {
		t.Fatal("no routes registered; router broken?")
	}

	param := regexp.MustCompile(`\{([a-zA-Z_][a-zA-Z0-9_]*)(\.\.\.)?\}`)
	known := map[string]bool{}
	for _, name := range pathParamNames {
		known[name] = true
	}

	for _, r := range app.routes {
		for _, match := range param.FindAllStringSubmatch(r.pattern, -1) {
			if match[2] != "" {
				// Wildcard segments (e.g. {path...}) only serve local
				// content and are never formatted into an upstream URL.
				continue
			}
			if _, ok := known[match[1]]; !ok {
				t.Errorf("route %q uses parameter %q not covered by pathParamNames", r.pattern, match[1])
			}
		}
		if strings.HasPrefix(r.pattern, "/api/v1/") && r.wrapper != "pdns" {
			t.Errorf("route %q is guarded by %q, want pdns", r.pattern, r.wrapper)
		}
	}
}

// TestPathParamsValidatedFromPattern complements TestRouteCoverage by checking
// a concrete injected value end-to-end through the real mux.
func TestPathParamsValidatedFromPattern(t *testing.T) {
	up := "http://pdns.example"
	yaml := `pdns_api_url: "` + up + `"
pdns_api_token: "upstream"
environments:
  - name: "Test 1"
    token_sha512: ` + config.HashToken(testToken)
	cfg, err := config.Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	app := &App{Cfg: cfg, Conn: upstream.New(up, "upstream", true)}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/servers/localhost/zones/other.org.%3F.example.com./cryptokeys/1%3Fx", nil)
	req.Header.Set("X-API-Key", testToken)
	rec := httptest.NewRecorder()
	app.router().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
	if body := rec.Body.String(); !strings.Contains(body, "Invalid value for path parameter") {
		t.Errorf("unexpected body: %s", body)
	}
}

// TestRecoverPanicReportsPanic verifies the hook main wires to Sentry.
func TestRecoverPanicReportsPanic(t *testing.T) {
	reported := false
	app := &App{Cfg: &config.Config{PDNSAPIURL: "http://pdns.example"},
		Conn:          upstream.New("http://pdns.example", "token", true),
		PanicReporter: func(r *http.Request, recovered any) { reported = recovered == "boom" },
	}

	h := app.recoverPanic(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		panic("boom")
	}))
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", rec.Code)
	}
	if body := rec.Body.String(); !strings.Contains(body, "Unhandled error") {
		t.Errorf("unexpected body: %s", body)
	}
	if !reported {
		t.Error("PanicReporter was not called")
	}
}

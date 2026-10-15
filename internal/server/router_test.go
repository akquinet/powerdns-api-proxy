package server

import (
	"net/http"
	"net/http/httptest"
	"reflect"
	"regexp"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/upstream"
)

// TestRouteCoverage enforces the routing conventions:
//
//   - every path parameter forwarded into an upstream URL is known to
//     guardPathParams, so unknown parameters can never skip the injection
//     check;
//   - every /api/v1 endpoint comes from apiV1Routes and carries both the auth
//     and the path-param guard middleware.
//
// Adding a route with a new parameter provides no protection on its own:
// register it in apiV1Routes and add the parameter to pathParamNames.
func TestRouteCoverage(t *testing.T) {
	up := "http://pdns.example"
	app := &App{
		Cfg: &config.Config{
			PDNSAPIURL:     up,
			APIDocsEnabled: true,
		},
		Conn: upstream.New(up, "token", true),
	}

	authPtr := reflect.ValueOf(app.auth).Pointer()
	guardPtr := reflect.ValueOf(app.guardPathParams).Pointer()

	param := regexp.MustCompile(`\{([a-zA-Z_][a-zA-Z0-9_]*)\}`)
	known := map[string]bool{}
	for _, name := range pathParamNames {
		known[name] = true
	}

	fromTable := map[string]bool{}
	for _, rt := range app.apiV1Routes() {
		full := "/api/v1" + rt.pattern
		fromTable[rt.method+" "+full] = true
		for _, match := range param.FindAllStringSubmatch(full, -1) {
			if !known[match[1]] {
				t.Errorf("apiV1Routes entry %s %s uses parameter %q not covered by pathParamNames", rt.method, full, match[1])
			}
		}
	}

	seen := 0
	err := chi.Walk(app.router(), func(method, route string, _ http.Handler, mws ...func(http.Handler) http.Handler) error {
		seen++
		if strings.HasPrefix(route, "/api/v1/") {
			if !hasMiddleware(mws, authPtr) {
				t.Errorf("route %s %s is missing the auth middleware", method, route)
			}
			if !hasMiddleware(mws, guardPtr) {
				t.Errorf("route %s %s is missing guardPathParams", method, route)
			}
			if !fromTable[method+" "+route] {
				t.Errorf("route %s %s is not registered via apiV1Routes", method, route)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walking routes: %v", err)
	}
	if seen == 0 {
		t.Fatal("no routes registered; router broken?")
	}
}

// hasMiddleware reports whether the route's middleware chain contains fn,
// compared by function pointer.
func hasMiddleware(mws []func(http.Handler) http.Handler, ptr uintptr) bool {
	for _, mw := range mws {
		if reflect.ValueOf(mw).Pointer() == ptr {
			return true
		}
	}
	return false
}

// TestPathParamsValidatedFromPattern complements TestRouteCoverage by checking
// a concrete injected value end-to-end through the real router.
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

	h := app.recoverer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
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

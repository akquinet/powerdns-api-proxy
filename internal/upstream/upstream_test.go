package upstream

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/akquinet/powerdns-api-proxy/internal/logging"
)

func captureLogs(t *testing.T) *bytes.Buffer {
	t.Helper()
	buf := &bytes.Buffer{}
	original := logging.Log
	logging.Log = logging.New(logging.LevelDebug, "text")
	logging.Log.SetOutput(buf)
	t.Cleanup(func() { logging.Log = original })
	return buf
}

func TestSensitivePayloadRedacted(t *testing.T) {
	buf := captureLogs(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.ReadAll(r.Body)
		_, _ = w.Write([]byte(`{"key":"SUPER_SECRET_TSIG_KEY"}`))
	}))
	defer srv.Close()

	conn := New(srv.URL, "upstream-token", true)
	body := []byte(`{"name":"test","key":"SUPER_SECRET_TSIG_KEY"}`)
	if _, err := conn.Request(context.Background(), http.MethodPost,
		"/api/v1/servers/localhost/tsigkeys", nil, body); err != nil {
		t.Fatalf("request: %v", err)
	}

	logs := buf.String()
	if strings.Contains(logs, "SUPER_SECRET_TSIG_KEY") {
		t.Errorf("secret leaked into logs: %s", logs)
	}
	if !strings.Contains(logs, "<redacted>") {
		t.Errorf("expected redaction marker in logs: %s", logs)
	}
}

func TestNonSensitivePathLogged(t *testing.T) {
	buf := captureLogs(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"name":"example.com."}`))
	}))
	defer srv.Close()

	conn := New(srv.URL, "upstream-token", true)
	if _, err := conn.Request(context.Background(), http.MethodGet,
		"/api/v1/servers/localhost/zones/example.com.", nil, nil); err != nil {
		t.Fatalf("request: %v", err)
	}
	if !strings.Contains(buf.String(), "example.com.") {
		t.Errorf("expected path in logs: %s", buf.String())
	}
}

func TestZoneNamedLikeSensitiveEndpointNotRedacted(t *testing.T) {
	buf := captureLogs(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"name":"tsigkeys.example.com."}`))
	}))
	defer srv.Close()

	conn := New(srv.URL, "upstream-token", true)
	if _, err := conn.Request(context.Background(), http.MethodGet,
		"/api/v1/servers/localhost/zones/tsigkeys.example.com./rrsets", nil, nil); err != nil {
		t.Fatalf("request: %v", err)
	}
	if strings.Contains(buf.String(), "<redacted>") {
		t.Errorf("zone named like sensitive endpoint must not be redacted: %s", buf.String())
	}
}

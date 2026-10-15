package logging

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func newTestLogger(t *testing.T, format string) (*Logger, *bytes.Buffer) {
	t.Helper()
	buf := &bytes.Buffer{}
	l := New(LevelInfo, format)
	l.SetOutput(buf)
	return l, buf
}

func firstJSON(t *testing.T, buf *bytes.Buffer) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(buf.Bytes(), &out); err != nil {
		t.Fatalf("decode log JSON %q: %v", buf.String(), err)
	}
	return out
}

func TestAuditJSONFormat(t *testing.T) {
	l, buf := newTestLogger(t, "json")
	l.Audit("Test1", "DELETE", "/zones/test.com", 403, nil, nil, "")

	entry := firstJSON(t, buf)
	if entry["event_type"] != "audit" {
		t.Errorf("event_type = %v", entry["event_type"])
	}
	if _, ok := entry["message"]; ok {
		t.Error("audit entry must not carry a message field")
	}
	audit := entry["audit"].(map[string]any)
	if audit["environment"] != "Test1" || audit["status_code"] != float64(403) {
		t.Errorf("unexpected audit: %v", audit)
	}
	if _, ok := audit["client_ip"]; ok {
		t.Error("client_ip must be omitted when not provided")
	}
}

func TestAuditJSONPayloadAndQueryParams(t *testing.T) {
	l, buf := newTestLogger(t, "json")
	payload := map[string]any{"rrsets": []any{}}
	l.Audit("Test1", "PATCH", "/zones/example.com", 204, payload, nil, "")
	audit := firstJSON(t, buf)["audit"].(map[string]any)
	if _, ok := audit["payload"]; !ok {
		t.Error("expected payload in audit entry")
	}

	buf.Reset()
	l.Audit("Test1", "GET", "/search-data", 200, nil, map[string]string{"q": "test"}, "")
	audit = firstJSON(t, buf)["audit"].(map[string]any)
	if audit["query_params"].(map[string]any)["q"] != "test" {
		t.Errorf("unexpected query params: %v", audit["query_params"])
	}
}

func TestAuditRedactsSensitivePayload(t *testing.T) {
	l, buf := newTestLogger(t, "json")
	l.Audit("Test1", "POST", "/zones/example.com/cryptokeys", 201, map[string]any{"content": "secret"}, nil, "")
	audit := firstJSON(t, buf)["audit"].(map[string]any)
	if _, ok := audit["payload"]; ok {
		t.Error("payload must be redacted for sensitive endpoints")
	}
}

func TestAuditTextWithClientIP(t *testing.T) {
	l, buf := newTestLogger(t, "text")
	l.Audit("Test1", "PATCH", "/zones/example.com", 204, map[string]any{"rrsets": []any{}}, nil, "203.0.113.9")
	line := buf.String()
	if !strings.Contains(line, "AUDIT: Test1 203.0.113.9 PATCH /zones/example.com 204") {
		t.Errorf("unexpected text audit line: %s", line)
	}
	if !strings.Contains(line, "payload=") {
		t.Errorf("expected payload in line: %s", line)
	}
}

func TestAuditTextKeepsUnknownMarkerOut(t *testing.T) {
	l, buf := newTestLogger(t, "text")
	l.Audit("Test1", "GET", "/zones", 401, nil, nil, "unknown")
	if strings.Contains(buf.String(), "unknown") {
		t.Errorf("unknown marker must not appear in text line: %s", buf.String())
	}
}

func TestAuditJSONIncludesUnknownMarker(t *testing.T) {
	l, buf := newTestLogger(t, "json")
	l.Audit("Test1", "GET", "/zones", 401, nil, nil, "unknown")
	audit := firstJSON(t, buf)["audit"].(map[string]any)
	if audit["client_ip"] != "unknown" {
		t.Errorf("expected client_ip unknown, got %v", audit["client_ip"])
	}
}

package config

import (
	"errors"
	"testing"
)

func mustZone(t *testing.T, z Zone) *Zone {
	t.Helper()
	out, err := NewZone(z)
	if err != nil {
		t.Fatalf("NewZone: %v", err)
	}
	return out
}

func mustEnv(t *testing.T, e Environment) *Environment {
	t.Helper()
	if err := e.Finalize(); err != nil {
		t.Fatalf("Finalize: %v", err)
	}
	return &e
}

func TestZoneDefaultsAllRecordsAndACME(t *testing.T) {
	z := mustZone(t, Zone{Name: "example.com."})
	if !z.AllRecords {
		t.Error("expected all_records to be enabled when no records are defined")
	}
	if !z.Services.ACME {
		t.Error("expected acme to be enabled when no records are defined")
	}
}

func TestZoneWithRecordsKeepsAllRecordsOff(t *testing.T) {
	z := mustZone(t, Zone{Name: "example.com.", Records: []string{"a.example.com."}})
	if z.AllRecords {
		t.Error("expected all_records to stay disabled when records are defined")
	}
}

func TestGetZoneIfAllowed(t *testing.T) {
	env := mustEnv(t, Environment{
		Name:        "Test 1",
		TokenSHA512: HashToken("token"),
		Zones:       []*Zone{mustZone(t, Zone{Name: "test.example.com."})},
	})

	if z, err := env.GetZoneIfAllowed("test.example.com."); err != nil || z.Name != "test.example.com." {
		t.Fatalf("expected zone, got %v (%v)", z, err)
	}
	if _, err := env.GetZoneIfAllowed("test.example.com"); err != nil {
		t.Errorf("expected trailing-dot variant to match: %v", err)
	}
	if _, err := env.GetZoneIfAllowed("other.example.com."); !errors.Is(err, ErrZoneNotAllowed) {
		t.Errorf("expected ErrZoneNotAllowed, got %v", err)
	}
}

func TestGetZoneIfAllowedSubzone(t *testing.T) {
	env := mustEnv(t, Environment{
		Name:        "Test",
		TokenSHA512: HashToken("token"),
		Zones:       []*Zone{mustZone(t, Zone{Name: "example.com.", Subzones: true})},
	})
	if _, err := env.GetZoneIfAllowed("deep.sub.example.com."); err != nil {
		t.Errorf("expected subzone to match: %v", err)
	}
	if _, err := env.GetZoneIfAllowed("example.com.evil."); !errors.Is(err, ErrZoneNotAllowed) {
		t.Errorf("expected dotted-boundary rejection, got %v", err)
	}
}

func TestGetZoneIfAllowedRegex(t *testing.T) {
	env := mustEnv(t, Environment{
		Name:        "Test",
		TokenSHA512: HashToken("token"),
		Zones:       []*Zone{mustZone(t, Zone{Name: `.*\.example\.com`, Regex: true})},
	})
	if _, err := env.GetZoneIfAllowed("customer.example.com."); err != nil {
		t.Errorf("expected regex match: %v", err)
	}
	if _, err := env.GetZoneIfAllowed("evil.example.com.attacker.net"); !errors.Is(err, ErrZoneNotAllowed) {
		t.Errorf("expected no unanchored match, got %v", err)
	}
}

func TestEnvironmentForToken(t *testing.T) {
	raw := "lashflkashlfgkashglashglashgl"
	cfg := defaults()
	cfg.PDNSAPIURL = "https://pdns.example"
	cfg.PDNSAPIToken = "upstream"
	cfg.Environments = []*Environment{
		{Name: "Test 1", TokenSHA512: HashToken(raw)},
	}
	if err := cfg.validate(); err != nil {
		t.Fatalf("validate: %v", err)
	}

	if env := cfg.EnvironmentForToken(raw); env == nil || env.Name != "Test 1" {
		t.Fatalf("expected environment lookup, got %v", env)
	}
	if env := cfg.EnvironmentForToken("wrong"); env != nil {
		t.Errorf("expected nil for unknown token, got %v", env)
	}
}

func TestParseIndexHTML(t *testing.T) {
	raw := "lashflkashlfgkashglashglashgl"
	yaml := "pdns_api_url: \"https://test.example.com\"\n" +
		"pdns_api_token: \"testtoken\"\n" +
		"index_html: \"<html><body><h1>Custom Page</h1></body></html>\"\n" +
		"environments:\n  - name: \"Test\"\n    token_sha512: \"" + HashToken(raw) + "\"\n    zones:\n      - name: \"example.com\"\n"
	cfg, err := Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if cfg.IndexHTML != "<html><body><h1>Custom Page</h1></body></html>" {
		t.Errorf("unexpected index_html: %q", cfg.IndexHTML)
	}
	if !cfg.IndexEnabled {
		t.Error("expected index_enabled default true")
	}
}

func TestParseIndexDisabled(t *testing.T) {
	raw := "lashflkashlfgkashglashglashgl"
	yaml := "pdns_api_url: \"https://test.example.com\"\n" +
		"pdns_api_token: \"testtoken\"\n" +
		"index_enabled: false\n" +
		"environments:\n  - name: \"Test\"\n    token_sha512: \"" + HashToken(raw) + "\"\n"
	cfg, err := Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if cfg.IndexEnabled {
		t.Error("expected index_enabled false")
	}
}

func TestParseRejectsShortToken(t *testing.T) {
	yaml := "pdns_api_url: \"https://test.example.com\"\n" +
		"pdns_api_token: \"testtoken\"\n" +
		"environments:\n  - name: \"Test\"\n    token_sha512: \"tooshort\"\n"
	if _, err := Parse([]byte(yaml)); err == nil {
		t.Fatal("expected validation error for short token_sha512")
	}
}

func TestParseEmptyZonesIsEmptySlice(t *testing.T) {
	raw := "token"
	yaml := "pdns_api_url: \"https://test.example.com\"\n" +
		"pdns_api_token: \"testtoken\"\n" +
		"environments:\n  - name: \"Test\"\n    token_sha512: \"" + HashToken(raw) + "\"\n"
	cfg, err := Parse([]byte(yaml))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if cfg.Environments[0].Zones == nil {
		t.Error("expected empty (non-nil) zones slice")
	}
}

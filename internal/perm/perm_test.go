package perm

import (
	"testing"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
)

func zone(t *testing.T, z config.Zone) *config.Zone {
	t.Helper()
	out, err := config.NewZone(z)
	if err != nil {
		t.Fatalf("NewZone: %v", err)
	}
	return out
}

func env(t *testing.T, e config.Environment) *config.Environment {
	t.Helper()
	if err := e.Finalize(); err != nil {
		t.Fatalf("Finalize: %v", err)
	}
	return &e
}

func rrset(name string) config.RRSET {
	return config.RRSET{Name: name, Type: "TXT", ChangeType: "REPLACE", TTL: 3600}
}

func TestZoneAllowed(t *testing.T) {
	e := env(t, config.Environment{
		Name:        "Test",
		TokenSHA512: config.HashToken("t"),
		Zones:       []*config.Zone{zone(t, config.Zone{Name: "test.example.com."})},
	})
	if !ZoneAllowed(e, "test.example.com.") {
		t.Error("expected zone allowed")
	}
	if ZoneAllowed(e, "other.example.com.") {
		t.Error("expected zone denied")
	}

	e.GlobalReadOnly = true
	if !ZoneAllowed(e, "anything.example.com.") {
		t.Error("global_read_only should allow any zone")
	}
}

func TestZoneAdmin(t *testing.T) {
	e := env(t, config.Environment{
		Name:        "Test",
		TokenSHA512: config.HashToken("t"),
		Zones:       []*config.Zone{zone(t, config.Zone{Name: "test.example.com.", Admin: true})},
	})
	if !ZoneAdmin(e, "test.example.com.") {
		t.Error("expected admin")
	}
	if ZoneAdmin(e, "nope.example.com.") {
		t.Error("expected no admin for unknown zone")
	}
}

func TestRRSetAllowedAllRecords(t *testing.T) {
	z := zone(t, config.Zone{Name: "test-zone.example.com."})
	for _, name := range []string{
		"entry1.test-zone.example.com.",
		"entry2.entry1.test-zone.example.com",
		"test-zone.example.com.",
	} {
		if !RRSetAllowed(z, rrset(name)) {
			t.Errorf("expected %q allowed", name)
		}
	}
}

func TestRRSetAllowedSingleEntries(t *testing.T) {
	z := zone(t, config.Zone{
		Name: "test-zone.example.com.",
		Records: []string{
			"entry1.test-zone.example.com.",
			"entry2.entry1.test-zone.example.com",
			"test-zone.example.com.",
		},
	})
	for _, name := range []string{
		"entry1.test-zone.example.com.",
		"entry2.entry1.test-zone.example.com",
		"test-zone.example.com.",
	} {
		if !RRSetAllowed(z, rrset(name)) {
			t.Errorf("expected %q allowed", name)
		}
	}
	for _, name := range []string{
		"entry100.test-zone.example.com.",
		"test-record.example.com.",
	} {
		if RRSetAllowed(z, rrset(name)) {
			t.Errorf("expected %q denied", name)
		}
	}
}

func TestRRSetAllowedRegexZone(t *testing.T) {
	z := zone(t, config.Zone{
		Name:         ".*",
		Regex:        true,
		RegexRecords: []string{`^_acme-challenge\..*`},
	})
	if !RRSetAllowed(z, rrset("_acme-challenge.example.com.")) {
		t.Error("expected acme challenge allowed")
	}
	if RRSetAllowed(z, rrset("www.example.com.")) {
		t.Error("expected www denied")
	}
}

func TestRRSetAllowedSuffixWithoutDotBoundary(t *testing.T) {
	z := zone(t, config.Zone{Name: "example.com.", Records: []string{"allowed.example.com."}})
	if RRSetAllowed(z, rrset("evilexample.com.")) {
		t.Error("expected evilexample.com denied")
	}
}

func TestRRSetAllowedReadOnly(t *testing.T) {
	z := zone(t, config.Zone{Name: "test-zone.example.com.", ReadOnly: true})
	if RRSetAllowed(z, rrset("anything.test-zone.example.com.")) {
		t.Error("read_only must deny all writes")
	}
}

func TestACMERecordAllowed(t *testing.T) {
	withACME := zone(t, config.Zone{
		Name:     "test-zone.example.com",
		Records:  []string{"blabub.test-zone.example.com"},
		Services: config.Services{ACME: true},
	})
	if !ACMERecordAllowed(withACME, rrset("_acme-challenge.blabub.test-zone.example.com")) {
		t.Error("expected acme challenge allowed")
	}
	if ACMERecordAllowed(withACME, rrset("_acme.blabub.test-zone.example.com")) {
		t.Error("expected non-challenge denied")
	}

	withoutService := zone(t, config.Zone{
		Name:    "test-zone.example.com",
		Records: []string{"blabub.test-zone.example.com"},
	})
	if ACMERecordAllowed(withoutService, rrset("_acme-challenge.blabub.test-zone.example.com")) {
		t.Error("expected acme denied without service")
	}
}

func TestEnsureRRSetsAllowed(t *testing.T) {
	z := zone(t, config.Zone{
		Name:    "test-zone.example.com.",
		Records: []string{"test-zone.example.com."},
	})
	req := config.RRSETRequest{RRSets: []config.RRSET{
		rrset("entry1.test-zone.example.com."),
		rrset("test-zone.example.com."),
	}}
	err := EnsureRRSetsAllowed(z, req)
	apiErr, ok := err.(*httperr.Error)
	if !ok || apiErr.Status != 403 {
		t.Fatalf("expected 403 error, got %v", err)
	}
	if apiErr.Detail != "RRSET entry1.test-zone.example.com. not allowed" {
		t.Errorf("unexpected detail: %q", apiErr.Detail)
	}
}

func TestEnsureRRSetsAllowedReadOnly(t *testing.T) {
	z := zone(t, config.Zone{Name: "test-zone.example.com.", ReadOnly: true})
	err := EnsureRRSetsAllowed(z, config.RRSETRequest{})
	apiErr, ok := err.(*httperr.Error)
	if !ok || apiErr.Detail != "RRSET update not allowed with read only token" {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestGlobalPermissions(t *testing.T) {
	e := env(t, config.Environment{Name: "Test", TokenSHA512: config.HashToken("t")})
	if SearchAllowed(e, "q", "all") {
		t.Error("search should be denied by default")
	}
	e.GlobalSearch = true
	if !SearchAllowed(e, "q", "all") {
		t.Error("search should be allowed")
	}
	if TsigkeysAllowed(e) {
		t.Error("tsigkeys should be denied by default")
	}
	e.GlobalTsigkeys = true
	if !TsigkeysAllowed(e) {
		t.Error("tsigkeys should be allowed")
	}
	if ConfigAllowed(e) {
		t.Error("config should be denied by default")
	}
	e.GlobalConfig = true
	if !ConfigAllowed(e) {
		t.Error("config should be allowed")
	}
	if StatisticsAllowed(e) {
		t.Error("statistics should be denied by default")
	}
	e.GlobalStatistics = true
	if !StatisticsAllowed(e) {
		t.Error("statistics should be allowed")
	}
}

func TestCryptokeysAllowed(t *testing.T) {
	e := env(t, config.Environment{
		Name:        "Test",
		TokenSHA512: config.HashToken("t"),
		Zones:       []*config.Zone{zone(t, config.Zone{Name: "test.example.com.", Cryptokeys: true})},
	})
	if CryptokeysAllowed(e, "test") {
		t.Error("unknown zone should be denied")
	}
	if !CryptokeysAllowed(e, "test.example.com.") {
		t.Error("zone cryptokeys should be allowed")
	}
	e.GlobalCryptokeys = true
	if !CryptokeysAllowed(e, "test") {
		t.Error("global cryptokeys should be allowed")
	}
}

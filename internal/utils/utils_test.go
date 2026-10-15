package utils

import "testing"

func TestCheckSubzone(t *testing.T) {
	cases := []struct {
		zone, main string
		want       bool
	}{
		{"myzone.main.example.com", "main.example.com.", true},
		{"myzone.test.example.com", "main.example.com.", false},
		{"evilexample.com", "example.com", false},
		{"notexample.com.", "example.com.", false},
		{"example.com", "example.com.", true},
		{"example.com.", "example.com", true},
	}
	for _, c := range cases {
		if got := CheckSubzone(c.zone, c.main); got != c.want {
			t.Errorf("CheckSubzone(%q, %q) = %v, want %v", c.zone, c.main, got, c.want)
		}
	}
}

func TestCheckZonesEqual(t *testing.T) {
	if !CheckZonesEqual("myzone.main.example.com", "myzone.main.example.com.") {
		t.Error("expected equal ignoring trailing dot")
	}
	if CheckZonesEqual("a.example.com", "b.example.com") {
		t.Error("expected not equal")
	}
}

func TestMatchFull(t *testing.T) {
	matches := []struct{ zone, re string }{
		{"prod.customer.example.com", `.*customer.example.com`},
		{"prod.customer.example.com", `.*\.customer.example.com`},
		{"dns.prod.customer.example.com.", `.*customer.example.com`},
		{"prod.customer.example.com.", `\w+\.customer.example.com`},
		{"customer.example.com.", `\w*customer.example.com`},
		{"prod.customer.example.com.", `\w+\.\w+\.example.com`},
		{"_acme-challenge.service-test.example.com", `_acme-challenge\.service-.*\.example\.com`},
		{"service-42.example.com", `service-\d+\.example\.com`},
	}
	for _, c := range matches {
		re, err := CompileFullmatch(c.re)
		if err != nil {
			t.Fatalf("compile %q: %v", c.re, err)
		}
		if !MatchFull(re, c.zone) {
			t.Errorf("MatchFull(%q, %q) = false, want true", c.zone, c.re)
		}
	}

	nonMatches := []struct{ zone, re string }{
		{"main.example.com.", `\w+\.main.example.com`},
		{"subzone.zone.main.example.com.", `\w+\.main.example.com`},
		{"customer.example.com.", `main.example.com`},
		{"evil.example.com.attacker.com", `.*\.example\.com`},
		{"example.com.attacker.net", `example\.com`},
		{"_acme-challenge.service-test.example.com.attacker.net", `_acme-challenge\.service-.*\.example\.com`},
		{"test.example.comEVIL", `test\.example\.com`},
	}
	for _, c := range nonMatches {
		re, err := CompileFullmatch(c.re)
		if err != nil {
			t.Fatalf("compile %q: %v", c.re, err)
		}
		if MatchFull(re, c.zone) {
			t.Errorf("MatchFull(%q, %q) = true, want false", c.zone, c.re)
		}
	}
}

func TestCheckPathParamSafeTrue(t *testing.T) {
	values := []string{
		"localhost", "example.com.", "sub.example.com", "_acme.example.com.",
		"*.example.com.", "münchen.example.de.", "北京.example.cn.",
		"xn--mller-kva.de.", "=2F.com.", "=5Facme-challenge.example.com.",
		"=2A.example.com.", "=C3=BC.example.com.", "=2E",
	}
	for _, v := range values {
		if !CheckPathParamSafe(v) {
			t.Errorf("CheckPathParamSafe(%q) = false, want true", v)
		}
	}
}

func TestCheckPathParamSafeFalse(t *testing.T) {
	values := []string{
		"", ".", "..", "other.org.?.example.com.", "other.org.#.example.com.",
		"other.org./.example.com.", "other.org.%3F.example.com.",
		"other.org.\\.example.com.", "other.org. .example.com.",
		"other.org.\n.example.com.", "other.org.\x7f.example.com.", "a:b",
		"e\u0301xample.com.", "=2f.com.", "=2", "a=b",
	}
	for _, v := range values {
		if CheckPathParamSafe(v) {
			t.Errorf("CheckPathParamSafe(%q) = true, want false", v)
		}
	}
}

func TestIsSensitivePath(t *testing.T) {
	if !IsSensitivePath("/api/v1/servers/localhost/zones/example.com./cryptokeys/1") {
		t.Error("expected cryptokeys path to be sensitive")
	}
	if IsSensitivePath("/api/v1/servers/localhost/zones/tsigkeys.example.com./rrsets") {
		t.Error("zone named like tsigkeys must not be sensitive")
	}
}

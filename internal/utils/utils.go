// Package utils holds small, dependency-free helpers shared across the proxy:
// DNS name comparison, regex full-matching and path-parameter validation.
package utils

import (
	"regexp"
	"strings"
)

// SensitivePathSegments are the upstream path segments that carry secret
// material (DNSSEC private keys, TSIG secrets) and must be redacted from logs.
var SensitivePathSegments = map[string]struct{}{
	"cryptokeys": {},
	"tsigkeys":   {},
}

// IsSensitivePath reports whether a path points at a cryptokey or tsigkey
// endpoint. Matching is done on path segments rather than substrings, so a zone
// named e.g. "tsigkeys.example.com" is not mistaken for the /tsigkeys endpoint.
func IsSensitivePath(path string) bool {
	for _, segment := range strings.Split(path, "/") {
		if _, ok := SensitivePathSegments[segment]; ok {
			return true
		}
	}
	return false
}

// safePathParamPattern mirrors the Python allowlist. Path parameters are
// formatted into the upstream URL as is, so only characters the HTTP client
// cannot reinterpret may be passed on. Besides the raw characters PowerDNS
// allows in zone/key names, PowerDNS encodes any other byte of a zone id as
// "=XX" (uppercase hex), so those escapes are accepted too. Unlike Python's
// unicode-aware \w, RE2's \w is ASCII-only, so the classes are spelled out to
// keep IDN zone names working. Combining marks are intentionally excluded.
var safePathParamPattern = regexp.MustCompile(`\A(?:[\p{L}\p{Nd}_*.-]|=[0-9A-F]{2})+\z`)

// CheckPathParamSafe reports whether a path parameter can be forwarded to
// PowerDNS unchanged.
func CheckPathParamSafe(value string) bool {
	switch value {
	case "", ".", "..":
		return false
	}
	return safePathParamPattern.MatchString(value)
}

// CheckSubzone reports whether zone is a subzone of mainZone (or equal to it).
// A trailing dot is ignored on both sides and the dot boundary is enforced.
func CheckSubzone(zone, mainZone string) bool {
	zone = strings.TrimRight(zone, ".")
	mainZone = strings.TrimRight(mainZone, ".")
	return zone == mainZone || strings.HasSuffix(zone, "."+mainZone)
}

// CheckZonesEqual reports whether two names are equal, ignoring a trailing dot.
func CheckZonesEqual(zone1, zone2 string) bool {
	return strings.TrimRight(zone1, ".") == strings.TrimRight(zone2, ".")
}

// CompileFullmatch compiles pattern so that it only matches a whole string,
// mirroring Python's re.fullmatch.
func CompileFullmatch(pattern string) (*regexp.Regexp, error) {
	return regexp.Compile(`\A(?:` + pattern + `)\z`)
}

// MatchFull reports whether s (ignoring a trailing dot) fully matches re.
func MatchFull(re *regexp.Regexp, s string) bool {
	if re == nil {
		return false
	}
	return re.MatchString(strings.TrimRight(s, "."))
}

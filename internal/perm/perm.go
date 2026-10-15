// Package perm implements the proxy's authorization rules: which zones, records
// and server-wide resources an environment may access. The logic mirrors the
// original Python implementation.
package perm

import (
	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
	"github.com/akquinet/powerdns-api-proxy/internal/utils"
)

// ZoneAllowed reports whether a zone is accessible in the environment.
func ZoneAllowed(env *config.Environment, zone string) bool {
	if env.GlobalReadOnly {
		return true
	}
	_, err := env.GetZoneIfAllowed(zone)
	return err == nil
}

// ZoneAdmin reports whether the environment may administer the zone.
func ZoneAdmin(env *config.Environment, zone string) bool {
	z, err := env.GetZoneIfAllowed(zone)
	if err != nil {
		return false
	}
	return z.Admin
}

// SearchAllowed reports whether global search is permitted.
func SearchAllowed(env *config.Environment, query, objectType string) bool {
	return env.GlobalSearch
}

// CryptokeysAllowed reports whether DNSSEC key management is permitted.
func CryptokeysAllowed(env *config.Environment, zone string) bool {
	if env.GlobalCryptokeys {
		return true
	}
	z, err := env.GetZoneIfAllowed(zone)
	if err != nil {
		return false
	}
	return z.Cryptokeys
}

// TsigkeysAllowed reports whether TSIG key management is permitted.
func TsigkeysAllowed(env *config.Environment) bool {
	return env.GlobalTsigkeys
}

// ConfigAllowed reports whether reading the server config is permitted.
func ConfigAllowed(env *config.Environment) bool {
	return env.GlobalConfig
}

// StatisticsAllowed reports whether reading server statistics is permitted.
func StatisticsAllowed(env *config.Environment) bool {
	return env.GlobalStatistics
}

// RRSetAllowed reports whether a single RRSet may be written.
func RRSetAllowed(zone *config.Zone, rrset config.RRSET) bool {
	if zone.ReadOnly {
		return false
	}
	if zone.AllRecords {
		return true
	}
	if !zone.Regex &&
		!utils.CheckZonesEqual(rrset.Name, zone.Name) &&
		!utils.CheckSubzone(rrset.Name, zone.Name) {
		return false
	}
	for _, record := range zone.Records {
		if utils.CheckZonesEqual(rrset.Name, record) {
			return true
		}
	}
	for _, re := range zone.RecordRegexes() {
		if utils.MatchFull(re, rrset.Name) {
			return true
		}
	}
	return ACMERecordAllowed(zone, rrset)
}

// ACMERecordAllowed reports whether the RRSet is an ACME challenge record that
// the zone permits.
func ACMERecordAllowed(zone *config.Zone, rrset config.RRSET) bool {
	if zone.AllRecords {
		return true
	}
	if !zone.Services.ACME {
		return false
	}
	for _, record := range zone.Records {
		if utils.CheckZonesEqual("_acme-challenge."+record, rrset.Name) {
			return true
		}
	}
	return false
}

// EnsureRRSetsAllowed returns an error if any RRSet in the request is not
// allowed to be written to the zone.
func EnsureRRSetsAllowed(zone *config.Zone, req config.RRSETRequest) error {
	if zone.ReadOnly {
		return httperr.New(403, "RRSET update not allowed with read only token")
	}
	for _, rrset := range req.RRSets {
		if !RRSetAllowed(zone, rrset) {
			return httperr.New(403, "RRSET "+rrset.Name+" not allowed")
		}
	}
	return nil
}

// Package config defines the proxy configuration model and the runtime index
// built from it: token -> environment lookup and per-zone permission-aware
// zone resolution. Configuration is YAML and is read once at startup.
package config

import (
	"errors"
	"regexp"

	"github.com/akquinet/powerdns-api-proxy/internal/utils"
)

// ErrZoneNotAllowed is returned when a zone is not covered by an environment.
var ErrZoneNotAllowed = errors.New("zone not allowed")

// DefaultIndexHTML is served at "/" unless index_html overrides it.
const DefaultIndexHTML = `
    <html>
        <head>
            <title>PowerDNS API Proxy</title>
        </head>
        <body>
            <center>
            <h1>PowerDNS API Proxy</h1>
            <p><a href="/docs">Swagger Docs</a></p>
            <q>The Domain Name Server (DNS) is the Achilles heel of the Web.<br>
            The important thing is that it's managed responsibly.</q>
            <p style="margin-top: 1em; font-size: 0.9em; color: #666;">— Tim Berners-Lee</p>
            </center>
        </body>
    </html>
`

// Services toggles optional per-zone features.
type Services struct {
	ACME bool `yaml:"acme" json:"acme"`
}

// Zone describes the permissions granted for a single zone.
//
// name is the zone name; when Regex is set, name is treated as an RE2 pattern.
// Records and RegexRecords grant write access to individual records. Admin
// enables creating and deleting the zone, Subzones applies the same permissions
// to all subzones, Cryptokeys enables DNSSEC key management, ReadOnly disables
// all writes, and AllRecords is enabled automatically when neither Records nor
// RegexRecords is defined.
type Zone struct {
	Name         string   `yaml:"name" json:"name"`
	Regex        bool     `yaml:"regex" json:"regex"`
	Description  string   `yaml:"description" json:"description"`
	Records      []string `yaml:"records" json:"records"`
	RegexRecords []string `yaml:"regex_records" json:"regex_records"`
	Services     Services `yaml:"services" json:"services"`
	Admin        bool     `yaml:"admin" json:"admin"`
	Subzones     bool     `yaml:"subzones" json:"subzones"`
	AllRecords   bool     `yaml:"all_records" json:"all_records"`
	ReadOnly     bool     `yaml:"read_only" json:"read_only"`
	Cryptokeys   bool     `yaml:"cryptokeys" json:"cryptokeys"`

	nameRe    *regexp.Regexp
	recordRes []*regexp.Regexp
}

// NewZone returns a finalized copy of z with defaults applied and any regexes
// compiled.
func NewZone(z Zone) (*Zone, error) {
	if err := z.finalize(); err != nil {
		return nil, err
	}
	return &z, nil
}

func (z *Zone) finalize() error {
	z.recordRes = nil
	if z.Records == nil {
		z.Records = []string{}
	}
	if z.RegexRecords == nil {
		z.RegexRecords = []string{}
	}
	if len(z.Records) == 0 && len(z.RegexRecords) == 0 {
		z.AllRecords = true
		z.Services.ACME = true
	}
	if z.Regex {
		re, err := utils.CompileFullmatch(z.Name)
		if err != nil {
			return err
		}
		z.nameRe = re
	}
	for _, pattern := range z.RegexRecords {
		re, err := utils.CompileFullmatch(pattern)
		if err != nil {
			return err
		}
		z.recordRes = append(z.recordRes, re)
	}
	return nil
}

// NameRegex returns the compiled name regex when Regex is enabled, else nil.
func (z *Zone) NameRegex() *regexp.Regexp { return z.nameRe }

// RecordRegexes returns the compiled record regexes.
func (z *Zone) RecordRegexes() []*regexp.Regexp { return z.recordRes }

// Environment is a single API client: one token scoped to a set of zones and
// server-wide permissions.
type Environment struct {
	Name             string  `yaml:"name" json:"name"`
	TokenSHA512      string  `yaml:"token_sha512" json:"token_sha512"`
	Zones            []*Zone `yaml:"zones" json:"zones"`
	GlobalReadOnly   bool    `yaml:"global_read_only" json:"global_read_only"`
	GlobalSearch     bool    `yaml:"global_search" json:"global_search"`
	GlobalCryptokeys bool    `yaml:"global_cryptokeys" json:"global_cryptokeys"`
	GlobalTsigkeys   bool    `yaml:"global_tsigkeys" json:"global_tsigkeys"`
	GlobalConfig     bool    `yaml:"global_config" json:"global_config"`
	GlobalStatistics bool    `yaml:"global_statistics" json:"global_statistics"`
	MetricsProxy     bool    `yaml:"metrics_proxy" json:"metrics_proxy"`

	zonesLookup map[string]*Zone
}

// Finalize builds the zone lookup and finalizes every zone.
func (e *Environment) Finalize() error {
	if e.Zones == nil {
		e.Zones = []*Zone{}
	}
	e.zonesLookup = make(map[string]*Zone, len(e.Zones))
	for _, z := range e.Zones {
		if err := z.finalize(); err != nil {
			return err
		}
		e.zonesLookup[z.Name] = z
	}
	return nil
}

// GetZoneIfAllowed returns the zone config matching name, or ErrZoneNotAllowed.
func (e *Environment) GetZoneIfAllowed(name string) (*Zone, error) {
	if z, ok := e.zonesLookup[name]; ok {
		return z, nil
	}
	for _, z := range e.Zones {
		if utils.CheckZonesEqual(name, z.Name) {
			return z, nil
		}
		if z.Subzones && utils.CheckSubzone(name, z.Name) {
			return z, nil
		}
		if z.Regex && utils.MatchFull(z.nameRe, name) {
			return z, nil
		}
	}
	return nil, ErrZoneNotAllowed
}

// Config is the parsed proxy configuration.
type Config struct {
	PDNSAPIURL         string         `yaml:"pdns_api_url"`
	PDNSAPIToken       string         `yaml:"pdns_api_token"`
	PDNSAPIVerifySSL   bool           `yaml:"pdns_api_verify_ssl"`
	Environments       []*Environment `yaml:"environments"`
	MetricsEnabled     bool           `yaml:"metrics_enabled"`
	MetricsRequireAuth bool           `yaml:"metrics_require_auth"`
	APIDocsEnabled     bool           `yaml:"api_docs_enabled"`
	IndexEnabled       bool           `yaml:"index_enabled"`
	IndexHTML          string         `yaml:"index_html"`

	tokenEnvMap map[string]*Environment
}

// EnvironmentForToken returns the environment for a raw client token, or nil.
func (c *Config) EnvironmentForToken(token string) *Environment {
	if token == "" {
		return nil
	}
	return c.tokenEnvMap[HashToken(token)]
}

// RRSETRecord is a single record inside an RRSet.
type RRSETRecord struct {
	Content  string `json:"content"`
	Disabled bool   `json:"disabled"`
}

// RRSETComment is a comment attached to an RRSet.
type RRSETComment struct {
	Content    string `json:"content"`
	Account    string `json:"account"`
	ModifiedAt int64  `json:"modified_at"`
}

// RRSET is a PowerDNS resource record set.
type RRSET struct {
	Name       string         `json:"name"`
	Type       string         `json:"type"`
	ChangeType string         `json:"changetype"`
	TTL        int            `json:"ttl"`
	Records    []RRSETRecord  `json:"records"`
	Comments   []RRSETComment `json:"comments"`
}

// RRSETRequest is the body of a PATCH /zones/{zone_id} request.
type RRSETRequest struct {
	RRSets []RRSET `json:"rrsets"`
}

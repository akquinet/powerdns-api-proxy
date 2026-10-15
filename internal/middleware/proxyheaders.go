package middleware

import (
	"net"
	"net/http"
	"strings"
)

// ProxyHeaders rewrites the client address from X-Forwarded-For, but only when
// the immediate peer is trusted. Untrusted peers and their headers are ignored.
type ProxyHeaders struct {
	trusted *trustedSet
	next    http.Handler
}

// NewProxyHeaders builds the middleware from a FORWARDED_ALLOW_IPS-style spec.
func NewProxyHeaders(forwardedAllowIPs string, next http.Handler) *ProxyHeaders {
	return &ProxyHeaders{trusted: parseTrusted(forwardedAllowIPs), next: next}
}

// ServeHTTP implements http.Handler.
func (m *ProxyHeaders) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	peerHost, peerPort, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		peerHost = r.RemoteAddr
	}

	if m.trusted.trust(peerHost) {
		if client := m.clientFromForwarded(r.Header.Get("X-Forwarded-For")); client != "" {
			if peerPort != "" {
				r.RemoteAddr = net.JoinHostPort(client, peerPort)
			} else {
				r.RemoteAddr = client
			}
		}
	}
	m.next.ServeHTTP(w, r)
}

// clientFromForwarded walks the X-Forwarded-For chain from right to left and
// returns the first hop that is not a trusted proxy.
func (m *ProxyHeaders) clientFromForwarded(header string) string {
	if header == "" {
		return ""
	}
	hops := strings.Split(header, ",")
	for i := len(hops) - 1; i >= 0; i-- {
		hop := strings.TrimSpace(hops[i])
		if hop == "" {
			continue
		}
		if !m.trusted.trust(hop) {
			return hop
		}
	}
	return ""
}

// trustedSet decides whether a host is a trusted reverse proxy. A
// FORWARDED_ALLOW_IPS-style spec supports hostnames, IPs, CIDR ranges and "*".
type trustedSet struct {
	trustAll bool
	hosts    map[string]struct{}
	nets     []*net.IPNet
	ips      []net.IP
}

func parseTrusted(spec string) *trustedSet {
	set := &trustedSet{hosts: map[string]struct{}{}}
	for _, item := range strings.Split(spec, ",") {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		if item == "*" {
			set.trustAll = true
			continue
		}
		if _, cidr, err := net.ParseCIDR(item); err == nil {
			set.nets = append(set.nets, cidr)
			continue
		}
		if ip := net.ParseIP(item); ip != nil {
			set.ips = append(set.ips, ip)
			continue
		}
		set.hosts[item] = struct{}{}
	}
	return set
}

func (t *trustedSet) trust(host string) bool {
	if t.trustAll {
		return true
	}
	if _, ok := t.hosts[host]; ok {
		return true
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return false
	}
	for _, candidate := range t.ips {
		if candidate.Equal(ip) {
			return true
		}
	}
	for _, network := range t.nets {
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

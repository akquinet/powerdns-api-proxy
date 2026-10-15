package middleware

import (
	"net"
	"net/http"
	"strings"
)

// ProxyHeaders returns middleware that rewrites the client address from
// X-Forwarded-For, but only when the immediate peer is trusted. Untrusted
// peers and their headers are ignored.
func ProxyHeaders(forwardedAllowIPs string) func(http.Handler) http.Handler {
	trusted := parseTrusted(forwardedAllowIPs)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			peerHost, peerPort, err := net.SplitHostPort(r.RemoteAddr)
			if err != nil {
				peerHost = r.RemoteAddr
			}
			if trusted.trust(peerHost) {
				if client := clientFromForwarded(trusted, r.Header.Get("X-Forwarded-For")); client != "" {
					if peerPort != "" {
						r.RemoteAddr = net.JoinHostPort(client, peerPort)
					} else {
						r.RemoteAddr = client
					}
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

// clientFromForwarded walks the X-Forwarded-For chain from right to left and
// returns the first hop that is not a trusted proxy.
func clientFromForwarded(trusted *trustedSet, header string) string {
	if header == "" {
		return ""
	}
	hops := strings.Split(header, ",")
	for i := len(hops) - 1; i >= 0; i-- {
		hop := strings.TrimSpace(hops[i])
		if hop == "" {
			continue
		}
		if !trusted.trust(hop) {
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

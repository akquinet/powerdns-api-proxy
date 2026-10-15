package middleware

import (
	"fmt"
	"net/http"

	"github.com/akquinet/powerdns-api-proxy/internal/logging"
)

// AccessLog logs one line per request, equivalent to the previous uvicorn
// access log. It runs after ProxyHeaders so the logged client address reflects
// X-Forwarded-For for trusted peers.
type AccessLog struct {
	next http.Handler
}

// NewAccessLog wraps next with access logging.
func NewAccessLog(next http.Handler) *AccessLog {
	return &AccessLog{next: next}
}

// ServeHTTP implements http.Handler.
func (m *AccessLog) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	rec := NewResponseRecorder(w)
	m.next.ServeHTTP(rec, r)
	logging.Log.Info(fmt.Sprintf(`%s - "%s %s %s" %d`,
		r.RemoteAddr, r.Method, r.RequestURI, proto(r), rec.Status))
}

// proto reports the HTTP protocol version, defaulting like net/http logs do.
func proto(r *http.Request) string {
	if r.Proto == "" {
		return "HTTP/1.1"
	}
	return r.Proto
}

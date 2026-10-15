package middleware

import (
	"fmt"
	"net/http"

	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/akquinet/powerdns-api-proxy/internal/logging"
)

// AccessLog logs one line per request, equivalent to the previous uvicorn
// access log. It runs after ProxyHeaders so the logged client address reflects
// X-Forwarded-For for trusted peers.
func AccessLog() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			rec := chimw.NewWrapResponseWriter(w, r.ProtoMajor)
			next.ServeHTTP(rec, r)
			logging.Log.Info(fmt.Sprintf(`%s - "%s %s %s" %d`,
				r.RemoteAddr, r.Method, r.RequestURI, proto(r), status(rec.Status())))
		})
	}
}

// proto reports the HTTP protocol version, defaulting like net/http logs do.
func proto(r *http.Request) string {
	if r.Proto == "" {
		return "HTTP/1.1"
	}
	return r.Proto
}

// status reports the response status, defaulting like net/http does for
// handlers that never call WriteHeader.
func status(code int) int {
	if code == 0 {
		return http.StatusOK
	}
	return code
}

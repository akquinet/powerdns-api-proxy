// Package metrics exposes Prometheus metrics with the same series names and
// labels as the previous prometheus-fastapi-instrumentator setup.
package metrics

import (
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/prometheus/client_golang/prometheus"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
)

var highrBuckets = []float64{
	0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 3.5,
	4, 4.5, 5, 7.5, 10, 30, 60, math.Inf(1),
}

var lowrBuckets = []float64{0.1, 0.5, 1, math.Inf(1)}

// Metrics holds the instrumented collectors.
type Metrics struct {
	requests    *prometheus.CounterVec
	reqSize     *prometheus.SummaryVec
	respSize    *prometheus.SummaryVec
	latencyHigh prometheus.Histogram
	latencyLow  *prometheus.HistogramVec
	envRequests *prometheus.CounterVec
}

// New builds and registers the metric collectors.
func New(reg prometheus.Registerer) *Metrics {
	m := &Metrics{
		requests: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "http_requests_total",
			Help: "Total number of requests by method, status and handler.",
		}, []string{"method", "status", "handler"}),
		reqSize: prometheus.NewSummaryVec(prometheus.SummaryOpts{
			Name: "http_request_size_bytes",
			Help: "Content length of incoming requests by handler. Only value of header is respected. Otherwise ignored. No percentile calculated. ",
		}, []string{"handler"}),
		respSize: prometheus.NewSummaryVec(prometheus.SummaryOpts{
			Name: "http_response_size_bytes",
			Help: "Content length of outgoing responses by handler. Only value of header is respected. Otherwise ignored. No percentile calculated. ",
		}, []string{"handler"}),
		latencyHigh: prometheus.NewHistogram(prometheus.HistogramOpts{
			Name:    "http_request_duration_highr_seconds",
			Help:    "Latency with many buckets but no API specific labels. Made for more accurate percentile calculations. ",
			Buckets: highrBuckets,
		}),
		latencyLow: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "http_request_duration_seconds",
			Help:    "Latency with only few buckets by handler. Made to be only used if aggregation by handler is important. ",
			Buckets: lowrBuckets,
		}, []string{"method", "handler"}),
		envRequests: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "http_requests_environment",
			Help: "Total number of requests by environment, method, status and handler.",
		}, []string{"environment", "method", "status", "handler"}),
	}
	reg.MustRegister(m.requests, m.reqSize, m.respSize, m.latencyHigh, m.latencyLow, m.envRequests)
	return m
}

// Middleware records metrics for every request passing through it.
func (m *Metrics) Middleware(cfg *config.Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			rec := chimw.NewWrapResponseWriter(w, r.ProtoMajor)
			next.ServeHTTP(rec, r)
			duration := time.Since(start).Seconds()

			// The route pattern is only populated once the router has matched,
			// so it is read after the handler ran.
			handler := ""
			if routeCtx := chi.RouteContext(r.Context()); routeCtx != nil {
				handler = routeCtx.RoutePattern()
			}
			if handler == "" {
				handler = "none"
			}
			code := rec.Status()
			if code == 0 {
				code = http.StatusOK
			}
			status := strconv.Itoa(code)

			m.requests.WithLabelValues(r.Method, status, handler).Inc()
			reqLen := r.ContentLength
			if reqLen < 0 {
				reqLen = 0
			}
			m.reqSize.WithLabelValues(handler).Observe(float64(reqLen))
			m.respSize.WithLabelValues(handler).Observe(float64(rec.BytesWritten()))
			m.latencyHigh.Observe(duration)
			m.latencyLow.WithLabelValues(r.Method, handler).Observe(duration)

			if env := cfg.EnvironmentForToken(r.Header.Get("X-API-Key")); env != nil {
				m.envRequests.WithLabelValues(env.Name, r.Method, status, handler).Inc()
			}
		})
	}
}

package middleware

import (
	"bufio"
	"fmt"
	"net"
	"net/http"
)

// ResponseRecorder wraps an http.ResponseWriter while tracking the status code
// written and the number of body bytes written. Audit logging, the access log
// and metrics all use it to observe a request's outcome.
type ResponseRecorder struct {
	http.ResponseWriter
	Status  int
	Written int

	wroteHeader bool
}

// NewResponseRecorder wraps w.
func NewResponseRecorder(w http.ResponseWriter) *ResponseRecorder {
	return &ResponseRecorder{ResponseWriter: w, Status: http.StatusOK}
}

// WriteHeader implements http.ResponseWriter.
func (r *ResponseRecorder) WriteHeader(code int) {
	if !r.wroteHeader {
		r.Status = code
		r.wroteHeader = true
	}
	r.ResponseWriter.WriteHeader(code)
}

// Write implements http.ResponseWriter.
func (r *ResponseRecorder) Write(b []byte) (int, error) {
	if !r.wroteHeader {
		r.WriteHeader(http.StatusOK)
	}
	n, err := r.ResponseWriter.Write(b)
	r.Written += n
	return n, err
}

// WriteString implements io.StringWriter.
func (r *ResponseRecorder) WriteString(s string) (int, error) {
	return r.Write([]byte(s))
}

// Flush implements http.Flusher when the underlying writer supports it.
func (r *ResponseRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

// Hijack implements http.Hijacker when the underlying writer supports it.
func (r *ResponseRecorder) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	h, ok := r.ResponseWriter.(http.Hijacker)
	if !ok {
		return nil, nil, fmt.Errorf("underlying ResponseWriter does not support hijacking")
	}
	return h.Hijack()
}

// Unwrap gives net/http's ResponseController access to the original writer.
func (r *ResponseRecorder) Unwrap() http.ResponseWriter {
	return r.ResponseWriter
}

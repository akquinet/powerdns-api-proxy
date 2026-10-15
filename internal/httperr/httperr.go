// Package httperr defines the proxy's HTTP errors. Every error is serialised
// to the PowerDNS error format: {"error": "<detail>"}.
package httperr

// Error is an HTTP error carrying a status code and a client-facing detail.
type Error struct {
	Status int
	Detail string
}

func (e *Error) Error() string { return e.Detail }

// New builds an Error.
func New(status int, detail string) *Error {
	return &Error{Status: status, Detail: detail}
}

// ZoneNotAllowed is returned when a token has no access to a zone.
func ZoneNotAllowed() *Error { return New(403, "Zone not allowed") }

// ZoneAdminNotAllowed is returned when a token may not administer a zone.
func ZoneAdminNotAllowed() *Error { return New(403, "Not Zone admin") }

// RessourceNotAllowed is returned when a server-wide permission is missing.
func RessourceNotAllowed() *Error { return New(403, "Ressource not allowed") }

// InvalidPathParam is returned for a path parameter that cannot be forwarded.
func InvalidPathParam(name string) *Error {
	return New(400, "Invalid value for path parameter "+name)
}

// ServerNotFound is returned for any server id other than "localhost".
func ServerNotFound() *Error { return New(404, "Not Found") }

// NotAuthorized is returned when the token is unknown.
func NotAuthorized() *Error { return New(401, "Unauthorized") }

// SearchNotAllowed is returned when global_search is disabled.
func SearchNotAllowed() *Error { return New(403, "Search not allowed") }

// MetricsNotAllowed is returned when metrics_proxy is disabled.
func MetricsNotAllowed() *Error { return New(403, "Metrics not allowed") }

// Upstream is returned for unexpected upstream failures.
func Upstream(message string) *Error {
	if message == "" {
		message = "Error while connecting to PowerDNS backend"
	}
	return New(500, message)
}

// Unhandled is the fallback for errors that cannot be classified.
func Unhandled(message string) *Error {
	if message == "" {
		message = "Unhandled error"
	}
	return New(500, message)
}

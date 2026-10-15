// Package upstream talks to the PowerDNS Authoritative API on behalf of
// clients. A single pooled HTTP client is shared across all requests.
package upstream

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/akquinet/powerdns-api-proxy/internal/logging"
	"github.com/akquinet/powerdns-api-proxy/internal/utils"
)

// Response is a completed upstream reply with its raw body preserved.
type Response struct {
	StatusCode int
	Header     http.Header
	Body       []byte
	Data       any
}

// IsSuccess reports whether the status code is in the 2xx range.
func (r *Response) IsSuccess() bool {
	return r.StatusCode >= 200 && r.StatusCode < 300
}

// Connector is a PowerDNS API client backed by a shared connection pool.
type Connector struct {
	baseURL string
	token   string
	client  *http.Client
}

// New builds a Connector. verifySSL controls upstream certificate validation.
func New(baseURL, token string, verifySSL bool) *Connector {
	transport := &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 100,
		IdleConnTimeout:     90 * time.Second,
		ForceAttemptHTTP2:   true,
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: !verifySSL, //nolint:gosec // opt-out is explicit
		},
	}
	return &Connector{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		client:  &http.Client{Transport: transport, Timeout: 30 * time.Second},
	}
}

// Request performs an upstream request and returns the parsed response.
func (c *Connector) Request(ctx context.Context, method, path string, query url.Values, body []byte) (*Response, error) {
	fullURL := c.baseURL + path
	if len(query) > 0 {
		fullURL += "?" + query.Encode()
	}

	sensitive := utils.IsSensitivePath(path)
	loggedBody := string(body)
	if sensitive && len(body) > 0 {
		loggedBody = "<redacted>"
	}
	logging.Log.Info("Getting upstream PDNS API",
		"method", method,
		"path", fullURL,
		"payload", loggedBody,
	)

	var reader io.Reader
	if len(body) > 0 {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(ctx, method, fullURL, reader)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Key", c.token)

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	parsed := parseJSON(raw)
	loggedText := string(raw)
	if sensitive {
		loggedText = "<redacted>"
	}
	logging.Log.Debug("Got answer from upstream PDNS API",
		"status", resp.StatusCode,
		"text", loggedText,
	)

	return &Response{
		StatusCode: resp.StatusCode,
		Header:     resp.Header,
		Body:       raw,
		Data:       parsed,
	}, nil
}

func parseJSON(raw []byte) any {
	if len(raw) == 0 {
		return nil
	}
	var v any
	if err := json.Unmarshal(raw, &v); err != nil {
		return nil
	}
	return v
}

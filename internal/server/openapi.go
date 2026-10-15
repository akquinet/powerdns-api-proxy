package server

import (
	"embed"
	"net/http"
)

// docsAssets holds the index page and the hand-written OpenAPI spec. The
// Swagger UI assets themselves come from the swaggo/files module (pinned in
// go.mod), so no third-party blobs are vendored in this repository.
//
//go:embed web/index.html web/openapi.json
var docsAssets embed.FS

// handleDocsIndex serves the Swagger UI page.
func (a *App) handleDocsIndex(w http.ResponseWriter, r *http.Request) {
	data, err := docsAssets.ReadFile("web/index.html")
	if err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

// handleOpenAPI serves the proxy's OpenAPI specification.
func (a *App) handleOpenAPI(w http.ResponseWriter, r *http.Request) {
	data, err := docsAssets.ReadFile("web/openapi.json")
	if err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

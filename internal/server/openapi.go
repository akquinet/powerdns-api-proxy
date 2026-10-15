package server

import (
	"embed"
	"io/fs"
	"net/http"
)

//go:embed web
var webFS embed.FS

// handleDocs serves the embedded Swagger UI and its OpenAPI spec. The router
// only registers it when API docs are enabled.
func (a *App) handleDocs(w http.ResponseWriter, r *http.Request) {
	switch name := r.PathValue("path"); name {
	case "":
		a.serveDocFile(w, "web/index.html", "text/html; charset=utf-8")
	case "openapi.json":
		a.serveDocFile(w, "web/openapi.json", "application/json")
	case "swagger-ui.css":
		a.serveDocFile(w, "web/swagger-ui.css", "text/css; charset=utf-8")
	case "swagger-ui-bundle.js":
		a.serveDocFile(w, "web/swagger-ui-bundle.js", "application/javascript")
	default:
		http.NotFound(w, r)
	}
}

func (a *App) serveDocFile(w http.ResponseWriter, path, contentType string) {
	data, err := fs.ReadFile(webFS, path)
	if err != nil {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

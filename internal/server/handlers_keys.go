package server

import (
	"fmt"
	"net/http"

	"github.com/go-chi/chi/v5"

	"github.com/akquinet/powerdns-api-proxy/internal/config"
	"github.com/akquinet/powerdns-api-proxy/internal/httperr"
	"github.com/akquinet/powerdns-api-proxy/internal/logging"
	"github.com/akquinet/powerdns-api-proxy/internal/perm"
)

// keyedResource describes a permission-gated sub-resource with an optional
// trailing identifier (cryptokeys, tsigkeys). All its handlers share one
// implementation via App.handleKeyed.
type keyedResource struct {
	// allowed reports whether env may touch this resource.
	allowed func(env *config.Environment, r *http.Request) bool
	// base builds the collection's upstream path.
	base func(r *http.Request) string
	// keyParam is the path parameter naming a single item.
	keyParam string
	// logName is used in denial log lines.
	logName string
}

var cryptokeysResource = keyedResource{
	allowed: func(env *config.Environment, r *http.Request) bool {
		return perm.CryptokeysAllowed(env, chi.URLParam(r, "zone_id"))
	},
	base: func(r *http.Request) string {
		return zoneUpstreamPath(chi.URLParam(r, "server_id"), chi.URLParam(r, "zone_id")) + "/cryptokeys"
	},
	keyParam: "cryptokey_id",
	logName:  "CryptoKeys",
}

var tsigkeysResource = keyedResource{
	allowed: func(env *config.Environment, r *http.Request) bool {
		return perm.TsigkeysAllowed(env)
	},
	base: func(r *http.Request) string {
		return fmt.Sprintf("/api/v1/servers/%s/tsigkeys", chi.URLParam(r, "server_id"))
	},
	keyParam: "tsigkey_id",
	logName:  "TSIGKeys",
}

// handleKeyed forwards a keyed-resource request after checking permission.
// withKeyID appends the item identifier to the path; withBody forwards the
// request body. The forwarded HTTP method is the request method of the
// matched route.
func (a *App) handleKeyed(res keyedResource, withKeyID, withBody bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		env := envFrom(r)
		if env == nil {
			writeError(w, httperr.NotAuthorized())
			return
		}
		if !res.allowed(env, r) {
			logging.Log.Info(res.logName+" not allowed", "environment", env.Name)
			writeError(w, httperr.ZoneNotAllowed())
			return
		}
		path := res.base(r)
		if withKeyID {
			path += "/" + chi.URLParam(r, res.keyParam)
		}
		var body []byte
		if withBody {
			body = readBody(r)
		}
		a.forward(w, r, r.Method, path, nil, body)
	}
}

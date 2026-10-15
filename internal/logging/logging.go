// Package logging provides the proxy's structured text/JSON logger, including
// the audit log emitted for every /api/v1 request. It mirrors the original
// Python log shapes so existing log pipelines keep working.
package logging

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"

	lumberjack "gopkg.in/natefinch/lumberjack.v2"

	"github.com/akquinet/powerdns-api-proxy/internal/utils"
)

// Log is the process-wide logger. It is safe for concurrent use.
var Log = New(LevelDebug, "text")

// Level is a log severity.
type Level int

// Severities, ordered from least to most severe.
const (
	LevelDebug Level = iota
	LevelInfo
	LevelWarning
	LevelError
)

func (l Level) String() string {
	switch l {
	case LevelDebug:
		return "DEBUG"
	case LevelInfo:
		return "INFO"
	case LevelWarning:
		return "WARNING"
	case LevelError:
		return "ERROR"
	default:
		return "DEBUG"
	}
}

// ParseLevel maps a LOG_LEVEL-style string to a Level. Unknown values DEBUG.
func ParseLevel(s string) Level {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "INFO":
		return LevelInfo
	case "WARNING", "WARN":
		return LevelWarning
	case "ERROR":
		return LevelError
	default:
		return LevelDebug
	}
}

// Logger writes structured text or JSON lines.
type Logger struct {
	mu     sync.Mutex
	level  Level
	format string // "text" or "json"
	out    io.Writer
}

// New returns a logger writing to stderr.
func New(level Level, format string) *Logger {
	return &Logger{level: level, format: format, out: os.Stderr}
}

// SetOutput redirects the log output. Intended for tests.
func (l *Logger) SetOutput(w io.Writer) {
	l.mu.Lock()
	l.out = w
	l.mu.Unlock()
}

// Configure applies the LOG_LEVEL, LOG_FORMAT and LOG_FILE settings. A LOG_FILE
// of "" or "false" disables file logging. The file handler rotates at 100 MB
// with five backups, matching the previous behaviour.
func (l *Logger) Configure(level Level, format, file string) error {
	l.mu.Lock()
	l.level = level
	l.format = format
	var writers []io.Writer
	writers = append(writers, os.Stderr)
	if file != "" && !strings.EqualFold(file, "false") {
		writers = append(writers, &lumberjack.Logger{
			Filename:   file,
			MaxSize:    100,
			MaxBackups: 5,
		})
	}
	l.out = io.MultiWriter(writers...)
	l.mu.Unlock()
	return nil
}

func (l *Logger) log(level Level, msg string, extra map[string]any) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if level < l.level {
		return
	}
	now := time.Now().Format("2006-01-02T15:04:05")
	if l.format == "json" {
		module, function, line := caller()
		data := map[string]any{
			"timestamp":  now,
			"level":      level.String(),
			"event_type": "log",
			"logger":     "powerdns_api_proxy",
			"message":    msg,
			"module":     module,
			"function":   function,
			"line":       line,
		}
		for k, v := range extra {
			data[k] = v
		}
		_ = json.NewEncoder(l.out).Encode(data)
		return
	}
	module, function, line := caller()
	msg = appendExtras(msg, extra)
	fmt.Fprintf(l.out, "%s - %s - powerdns_api_proxy - %s - %s - %d - %s\n",
		level.String(), now, module, function, line, msg)
}

func appendExtras(msg string, extra map[string]any) string {
	if len(extra) == 0 {
		return msg
	}
	keys := make([]string, 0, len(extra))
	for k := range extra {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	b.WriteString(msg)
	for _, k := range keys {
		b.WriteString(" ")
		b.WriteString(k)
		b.WriteString("=")
		b.WriteString(fmt.Sprintf("%v", extra[k]))
	}
	return b.String()
}

// Debug logs at DEBUG level.
func (l *Logger) Debug(msg string, extra ...any) { l.log(LevelDebug, msg, kv(extra)) }

// Info logs at INFO level.
func (l *Logger) Info(msg string, extra ...any) { l.log(LevelInfo, msg, kv(extra)) }

// Warn logs at WARNING level.
func (l *Logger) Warn(msg string, extra ...any) { l.log(LevelWarning, msg, kv(extra)) }

// Error logs at ERROR level.
func (l *Logger) Error(msg string, extra ...any) { l.log(LevelError, msg, kv(extra)) }

func kv(pairs []any) map[string]any {
	if len(pairs) == 0 {
		return nil
	}
	m := make(map[string]any, len(pairs)/2)
	for i := 0; i+1 < len(pairs); i += 2 {
		if key, ok := pairs[i].(string); ok {
			m[key] = pairs[i+1]
		}
	}
	return m
}

func caller() (module, function string, line int) {
	pc, file, line, ok := runtime.Caller(2)
	if !ok {
		return "unknown", "unknown", 0
	}
	fn := runtime.FuncForPC(pc)
	function = "unknown"
	if fn != nil {
		function = fn.Name()
		if i := strings.LastIndex(function, "."); i >= 0 {
			function = function[i+1:]
		}
	}
	module = file
	if i := strings.LastIndex(file, "/"); i >= 0 {
		module = file[i+1:]
	}
	if i := strings.LastIndex(module, "."); i >= 0 {
		module = module[:i]
	}
	return module, function, line
}

// AuditData is the structured payload of an audit log entry.
type AuditData struct {
	Environment string            `json:"environment"`
	ClientIP    string            `json:"client_ip,omitempty"`
	Method      string            `json:"method"`
	Path        string            `json:"path"`
	StatusCode  int               `json:"status_code"`
	Payload     any               `json:"payload,omitempty"`
	QueryParams map[string]string `json:"query_params,omitempty"`
}

type auditEnvelope struct {
	Timestamp string    `json:"timestamp"`
	Level     string    `json:"level"`
	EventType string    `json:"event_type"`
	Audit     AuditData `json:"audit"`
}

// Audit logs one audited request. clientIP is only reported when non-empty;
// the sentinel "unknown" marks a peer address that was unavailable and only
// appears in JSON output, never in the text line, matching prior behaviour.
func (l *Logger) Audit(environment, method, path string, status int, payload any, queryParams map[string]string, clientIP string) {
	// Skip payload logging for sensitive endpoints.
	if payload != nil && utils.IsSensitivePath(path) {
		payload = nil
	}

	data := AuditData{
		Environment: environment,
		ClientIP:    clientIP,
		Method:      method,
		Path:        path,
		StatusCode:  status,
		Payload:     payload,
		QueryParams: queryParams,
	}

	l.mu.Lock()
	defer l.mu.Unlock()
	if LevelInfo < l.level {
		return
	}
	now := time.Now().Format("2006-01-02T15:04:05")

	if l.format == "json" {
		_ = json.NewEncoder(l.out).Encode(auditEnvelope{
			Timestamp: now,
			Level:     "INFO",
			EventType: "audit",
			Audit:     data,
		})
		return
	}

	identity := environment
	if clientIP != "" && clientIP != "unknown" {
		identity = environment + " " + clientIP
	}
	msg := fmt.Sprintf("AUDIT: %s %s %s %d", identity, method, path, status)
	if len(queryParams) > 0 {
		msg += " query_params=" + jsonString(queryParams)
	}
	if payload != nil {
		msg += " payload=" + jsonString(payload)
	}
	fmt.Fprintf(l.out, "%s - %s - powerdns_api_proxy - audit - audit - 0 - %s\n", "INFO", now, msg)
}

func jsonString(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Sprintf("%v", v)
	}
	return string(b)
}

package config

import (
	"crypto/sha512"
	"encoding/hex"
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// PathFromEnv returns the configuration path from PROXY_CONFIG_PATH.
func PathFromEnv() (string, error) {
	path := os.Getenv("PROXY_CONFIG_PATH")
	if path == "" {
		return "", fmt.Errorf("PROXY_CONFIG_PATH is not set")
	}
	return path, nil
}

// LoadFromEnv loads the configuration pointed at by PROXY_CONFIG_PATH.
func LoadFromEnv() (*Config, error) {
	path, err := PathFromEnv()
	if err != nil {
		return nil, err
	}
	return Load(path)
}

// Load reads and validates the YAML configuration at path.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading config %q: %w", path, err)
	}
	return Parse(data)
}

// Parse validates an in-memory YAML configuration.
func Parse(data []byte) (*Config, error) {
	cfg := defaults()
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parsing config: %w", err)
	}
	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

// HashToken returns the lowercase hex SHA-512 digest of a raw client token.
func HashToken(token string) string {
	sum := sha512.Sum512([]byte(token))
	return hex.EncodeToString(sum[:])
}

func defaults() *Config {
	return &Config{
		PDNSAPIVerifySSL:   true,
		MetricsEnabled:     true,
		MetricsRequireAuth: true,
		APIDocsEnabled:     true,
		IndexEnabled:       true,
		IndexHTML:          DefaultIndexHTML,
	}
}

func (c *Config) validate() error {
	if c.PDNSAPIURL == "" {
		return fmt.Errorf("pdns_api_url must be a non-empty string")
	}
	if c.PDNSAPIToken == "" {
		return fmt.Errorf("pdns_api_token must be a non-empty string")
	}
	c.tokenEnvMap = make(map[string]*Environment, len(c.Environments))
	for i, env := range c.Environments {
		if env.Name == "" {
			return fmt.Errorf("environment %d: name must be a non-empty string", i)
		}
		if len(env.TokenSHA512) != 128 {
			return fmt.Errorf("environment %q: token_sha512 must be 128 characters long", env.Name)
		}
		if _, err := hex.DecodeString(env.TokenSHA512); err != nil {
			return fmt.Errorf("environment %q: token_sha512 must be hex-encoded", env.Name)
		}
		if err := env.Finalize(); err != nil {
			return fmt.Errorf("environment %q: %w", env.Name, err)
		}
		c.tokenEnvMap[env.TokenSHA512] = env
	}
	return nil
}

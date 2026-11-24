# Vendored Swagger UI assets

Version: 5.36.0

Source: <https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-5.36.0.tgz>

These files are served by the proxy at `/static/swagger-ui`. They are copied
byte-for-byte from the `swagger-ui-dist` npm release, including the upstream
licence files required by its Apache-2.0 licence.

## Checksums

```text
7eb9f5a125e4bc9b3f0b71869b66d1a3d7c501f972f53d44ef91c2ae6c5bda5e  swagger-ui.css
b164c5a22535e40dae08c00271674a67e437ec195098c55fcedf8ffac7ac3c88  swagger-ui-bundle.js
3ed612f41e050ca5e7000cad6f1cbe7e7da39f65fca99c02e99e6591056e5837  favicon-32x32.png
```

## Updating

Set `SWAGGER_UI_VERSION` and run this from the repository root:

```shell
SWAGGER_UI_VERSION=5.36.0
curl -sL "https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-${SWAGGER_UI_VERSION}.tgz" |
  tar -xz --strip-components=1 -C powerdns_api_proxy/static/swagger-ui \
    package/swagger-ui.css \
    package/swagger-ui-bundle.js \
    package/favicon-32x32.png \
    package/LICENSE \
    package/NOTICE \
    package/swagger-ui-bundle.js.LICENSE.txt
```

Then update the version and checksums in this file. The stylesheet and script
reference source maps at the end of the files; those maps are not shipped, so
browsers only request them when developer tools are open.

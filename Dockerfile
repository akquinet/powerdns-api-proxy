FROM docker.io/golang:1.27-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY cmd ./cmd
COPY internal ./internal

ARG VERSION=dev
RUN CGO_ENABLED=0 go build -trimpath \
    -ldflags "-s -w -X main.version=${VERSION}" \
    -o /out/powerdns-api-proxy ./cmd/powerdns-api-proxy


FROM docker.io/alpine:3.21

# jq is shipped for parsing JSON audit logs (see README).
# hadolint ignore=DL3018
RUN apk add --no-cache jq \
    && adduser -D -u 1000 appuser

COPY --from=builder /out/powerdns-api-proxy /usr/local/bin/powerdns-api-proxy

USER appuser

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/powerdns-api-proxy"]

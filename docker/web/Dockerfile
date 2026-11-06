# Retro TV guide viewer: nginx serving the static app and the read-only
# ErsatzTV proxy. The unprivileged image runs as uid 101 and listens on 8080.
#
# The same image can also run as the "uplink" (compose.uplink.yaml): that
# service points NGINX_ENVSUBST_TEMPLATE_DIR at the second template.
FROM nginxinc/nginx-unprivileged:1.31.7-alpine

# Only these are filled into the nginx config from the environment.
ENV NGINX_ENVSUBST_FILTER="^(ERSATZTV_URL|UPLINK_BIND|UPLINK_PORT)$" \
    HEALTH_URL=http://127.0.0.1:8080/healthz

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY uplink/uplink.conf.template /etc/nginx/uplink-templates/default.conf.template
COPY app/ /usr/share/nginx/html/

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- "$HEALTH_URL" || exit 1

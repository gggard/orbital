# Shared base image for hosted static-site apps (SPEC §5.2).
# One shared image; apps layer their static/build output on top via COPY in
# the per-app generated Dockerfile.orbital (see orbital.k8s.scripts.DETECT_SH).
FROM nginx:1.27-alpine

RUN addgroup -g 1000 appuser \
    && adduser -D -u 1000 -G appuser appuser \
    && rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /usr/share/nginx/html \
    && chown -R 1000:1000 /usr/share/nginx/html

COPY nginx.conf /etc/nginx/nginx.conf

USER 1000
ENV HOME=/home/appuser
EXPOSE 8501

# /tmp is the only writable path under readOnlyRootFilesystem (SPEC §5.3);
# nginx.conf points pid/temp paths there, so it must exist before nginx starts.
CMD ["sh", "-c", "mkdir -p /tmp/nginx/client_temp /tmp/nginx/proxy_temp /tmp/nginx/fastcgi_temp /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp && exec nginx -g 'daemon off;'"]

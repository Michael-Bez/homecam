FROM nginx:1.27-alpine

# Remove the default config; we provide our own.
RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/nginx.conf

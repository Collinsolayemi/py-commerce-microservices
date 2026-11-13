FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/index.html frontend/styles.css frontend/app.js frontend/api.js frontend/store.js frontend/motion.js /usr/share/nginx/html/
COPY frontend/assets /usr/share/nginx/html/assets
EXPOSE 80

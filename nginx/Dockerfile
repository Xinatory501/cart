FROM alpine:3.18

RUN apk add --no-cache nginx openssl

# Создаем папки под логи и SSL
RUN mkdir -p /run/nginx /etc/nginx/ssl

# Генерируем самоподписанный сертификат на 10 лет (разработка/тесты)
# Для продакшена вы можете примонтировать свои Let's Encrypt ключи
RUN openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/nginx.key \
    -out /etc/nginx/ssl/nginx.crt \
    -subj "/C=BY/L=Minsk/O=CartaMe/CN=localhost"

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]

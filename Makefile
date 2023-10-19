export DOCKER_DEFAULT_PLATFORM=linux/amd64

up:
	docker compose -f docker-compose-local.yaml up -d

up_rebuild:
	docker compose -f docker-compose-local.yaml up --build -d

down:
	docker compose -f docker-compose-local.yaml down --remove-orphans

up_deploy:
	docker compose -f docker-compose-deploy.yaml up -d

up_deploy_rebuild:
	docker compose -f docker-compose-deploy.yaml up --build -d

down_deploy:
	docker compose -f docker-compose-deploy.yaml down --remove-orphans

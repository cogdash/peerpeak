#!/bin/sh
branch="$(git symbolic-ref --short HEAD 2>/dev/null)"
if [ "$branch" = "main" ]; then
	echo "Commiting directly to the main branch is prohibited!"
	exit 1
fi

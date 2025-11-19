#!/usr/bin/bash

find ./generated/ -maxdepth 1 -name "*.yml" -exec rm -v "{}" \;

while read -r f
do
	echo "Processing: $f"
	yq -y . "$f" > "./generated/$f"
done <<< $(find ./ -maxdepth 1 -name "*.yml")

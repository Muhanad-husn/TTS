# Start the TTS server and launch read_aloud in Docker

New-Item -ItemType Directory -Force -Path input, output | Out-Null

# Copy file arguments into input/ and rewrite paths for container
$containerArgs = @()
foreach ($arg in $args) {
    if (Test-Path -LiteralPath $arg -PathType Leaf) {
        $name = Split-Path $arg -Leaf
        Copy-Item -LiteralPath $arg -Destination "input/$name" -Force
        $containerArgs += "/input/$name"
    } else {
        $containerArgs += $arg
    }
}

docker compose up -d pocket-tts-wyoming
docker compose run --rm read-aloud @containerArgs

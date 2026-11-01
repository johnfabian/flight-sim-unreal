// Local-only adapter around Epic's UE 5.8 signalling server. No external services.
const path = require('node:path');
const http = require('node:http');
const { createRequire } = require('node:module');
const fromEpic = createRequire(path.join(__dirname, 'Infrastructure/package.json'));
const express = fromEpic('express');
const { SignallingServer, InitLogging } = fromEpic('@epicgames-ps/lib-pixelstreamingsignalling-ue5.8');
InitLogging({ logDir: path.join(__dirname, '../artifacts/streaming-logs'), logLevelConsole: 'info' });
const app = express();
const webRoot = path.join(__dirname, 'Infrastructure/SignallingWebServer/www');
app.get('/health', (_req, res) => res.json({ app: 'Aeronaut', mode: 'localhost' }));
app.get('/', (_req, res) => res.sendFile(path.join(__dirname, 'player.html')));
app.use(express.static(webRoot));
const httpServer = http.createServer(app);
httpServer.on('error', error => { console.error(error.message); process.exit(1); });
new SignallingServer({
    httpServer, streamerPort: 8888, streamerWsOptions: { host: '127.0.0.1' },
    peerOptions: { iceServers: [] }, maxSubscribers: 1
});
httpServer.listen(8080, '127.0.0.1', () => console.log('AERONAUT_STREAM_READY http://127.0.0.1:8080'));

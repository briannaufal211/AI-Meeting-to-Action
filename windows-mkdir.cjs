// Windows compatibility: same mkdir operation, executed synchronously to avoid
// permission failures on libuv worker threads in restricted desktop sessions.
const fs=require('node:fs');
fs.promises.mkdir=async function(path,options){return fs.mkdirSync(path,options)};

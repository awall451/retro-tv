# Server settings pieces

One `*.sh` file per feature that has a setting on the server. Each is
sourced by `../config.envsh` (in the container and by the Pi box's
`setup.sh`) and adds its key to `/config.json` with `config_set`, and any
site the page must reach to the CSP with `csp_frame` / `csp_connect`.
The rules a piece must follow are at the top of `../config.envsh`.

The app reads the file through `js/config.js`:

```js
import { serverSetting } from './config.js';
const idle = await serverSetting('idle');   // undefined when not set
```

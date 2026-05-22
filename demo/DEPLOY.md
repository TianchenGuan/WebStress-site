# Deploying the WebStress demo to Hugging Face Spaces

Step-by-step recipe to get a public live-play backend up at, e.g.,
`https://tianchenguan-webstress-demo.hf.space`.

## 1. Create the Space

1. Go to <https://huggingface.co/new-space>.
2. **Owner**: your HF account (e.g. `TianchenGuan`).
3. **Space name**: `webstress-demo` (lowercase, hyphenated).
4. **SDK**: Docker.
5. **Visibility**: Public.
6. **Hardware**: CPU basic (free).

Don't pick a Docker template — we ship our own Dockerfile.

## 2. Push the demo content

```bash
git clone https://huggingface.co/spaces/<your-user>/webstress-demo
cd webstress-demo

# Copy the two files from WebStress-site/demo/ into the Space repo root.
cp /path/to/WebStress-site/demo/Dockerfile .
cp /path/to/WebStress-site/demo/README.md .

git add Dockerfile README.md
git commit -m "init: WebStress demo Dockerfile + Space metadata"
git push
```

The Space build kicks off automatically. Click the *Logs* tab in the
Space UI to follow along — expect:

- ~30 s pulling base images
- ~2–4 min `pnpm install` + `pnpm build` (7 SPAs)
- ~30 s `pip install`
- ~10 s `git clone` of the WebStress repo
- ~5 s container start

So roughly **5 minutes total** for the first build. Subsequent builds
(triggered by a push) are similar.

## 3. Verify

Once the Space says **Running**:

```bash
curl -sI https://<your-user>-webstress-demo.hf.space/launch
# HTTP/2 200
```

Open `https://<your-user>-webstress-demo.hf.space/launch` in a browser
— you should see the WebStress task launcher. Pick a task (Gmail or
Amazon for fastest demo), click *Launch*, and the env tab should open
on the simulated site.

## 4. Wire the website to it

Edit `WebStress-site/site/src/lib/config.ts`:

```ts
export const LIVE_DEMO_URL = "https://<your-user>-webstress-demo.hf.space";
```

Then rebuild + push:

```bash
cd WebStress-site/site
npm run build
git -C .. add site/src/lib/config.ts
git -C .. commit -m "site: point live demo at HF Space"
git -C .. push
```

The "Try this task in the live demo →" buttons on
`/tasks/:task_id` now open the HF Space launcher in a new tab.

## 5. Optional: custom subdomain

If you want `demo.webstress.dev` instead of the long HF URL:

1. In Vercel (where `webstress.dev` is served from), add a CNAME record
   under DNS: `demo` → `<your-user>-webstress-demo.hf.space`.
2. In the HF Space settings, add `demo.webstress.dev` to *Custom
   domains*. HF will issue a TLS cert via Let's Encrypt.
3. Bump `LIVE_DEMO_URL` to `https://demo.webstress.dev` and redeploy
   the site.

## Troubleshooting

- **Build OOM** (rare on CPU basic, 16 GB RAM). The `pnpm build` step
  is the heaviest. If it fails, bump the Space to *CPU upgrade* ($0.03/h)
  for a one-off rebuild — once the SPAs are in the image cache, you
  can drop back to CPU basic.
- **Cold start > 30 s**. HF Spaces wake on first HTTP request. Pre-warm
  by hitting `/launch` once before linking visitors in.
- **`/control/...` returns 401**. By design — the demo doesn't expose
  the intervention controller. Human play through `/launch` works
  without the secret.
- **Frontend bundle missing**. Look for `WEBSTRESS_AUTO_BUILD_FRONTENDS=0`
  in the Space logs. If the build stage failed, the `webstress/static/envs/`
  copy was empty and the launcher will say "Environment backend exists
  but the frontend bundle has not been built." Trigger a rebuild from
  the Space *Settings* → *Factory rebuild*.

## Tear-down

`Settings → Delete this Space` in the HF Space UI. The Dockerfile and
config in this repo are unaffected, so re-deploying later is a 5-minute
`git push`.

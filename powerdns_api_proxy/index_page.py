"""Built-in index page served at ``/``.

The page is intentionally self-contained: all styling is inline CSS and there
are no external assets (fonts, scripts, images), so it works offline and adds
no network dependency. It uses a solid dark backdrop with small outlined
geometric shapes drifting across the screen, and it honors
``prefers-reduced-motion`` by disabling the animations.
"""

DEFAULT_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PowerDNS API Proxy</title>
<style>
  body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0b0f1a;
    color: #e6e9f0;
    font-family: system-ui, sans-serif;
  }

  main { padding: 2rem; text-align: center; }

  h1 { margin: 0 0 1rem; font-size: clamp(1.8rem, 5vw, 3rem); }

  .actions { display: flex; gap: 0.75rem; justify-content: center; }

  a {
    padding: 0.6rem 1.4rem;
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: 6px;
    color: inherit;
    text-decoration: none;
    font-weight: 600;
  }

  a:hover, a:focus {
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.5);
    outline: none;
  }

  blockquote { margin: 2rem 0 0; max-width: 34rem; line-height: 1.6; color: #b9bfce; }

  .attribution { margin: 0.75rem 0 0; font-size: 0.85rem; color: #737b8f; }

  .bg { position: fixed; inset: 0; overflow: hidden; pointer-events: none; }

  .shape {
    position: absolute;
    left: var(--x);
    top: var(--y);
    width: 10px;
    height: 10px;
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 2px;
    animation: drift 66s linear infinite;
    animation-delay: calc(66s * var(--p) * -1);
  }

  .shape.rtl { --tx: -125vw; }
  .shape.ttb { --tx: 0; --ty: 125vh; }
  .shape.btt { --tx: 0; --ty: -125vh; }
  .shape.round { border-radius: 50%; }
  .shape.tri { border: 0; background: rgba(255, 255, 255, 0.14); clip-path: polygon(50% 0, 100% 100%, 0 100%); }

  @keyframes drift { to { transform: translate(var(--tx, 125vw), var(--ty, 0)); } }

  @media (prefers-reduced-motion: reduce) { .shape { animation: none; } }
</style>
</head>
<body>
  <div class="bg" aria-hidden="true">
    <span class="shape" style="--x:-8%;--y:12%;--p:.37"></span>
    <span class="shape" style="--x:-12%;--y:40%;--p:.91"></span>
    <span class="shape tri" style="--x:-6%;--y:68%;--p:.12"></span>
    <span class="shape round" style="--x:-10%;--y:84%;--p:.68"></span>
    <span class="shape" style="--x:-9%;--y:26%;--p:.45"></span>
    <span class="shape round" style="--x:-11%;--y:55%;--p:.03"></span>
    <span class="shape rtl" style="--x:104%;--y:18%;--p:.79"></span>
    <span class="shape rtl tri" style="--x:106%;--y:46%;--p:.26"></span>
    <span class="shape rtl round" style="--x:102%;--y:74%;--p:.55"></span>
    <span class="shape rtl" style="--x:108%;--y:30%;--p:.83"></span>
    <span class="shape rtl" style="--x:105%;--y:60%;--p:.19"></span>
    <span class="shape rtl round" style="--x:103%;--y:90%;--p:.62"></span>
    <span class="shape ttb" style="--x:14%;--y:-8%;--p:.08"></span>
    <span class="shape ttb tri" style="--x:38%;--y:-10%;--p:.74"></span>
    <span class="shape ttb round" style="--x:58%;--y:-6%;--p:.41"></span>
    <span class="shape ttb" style="--x:78%;--y:-9%;--p:.96"></span>
    <span class="shape ttb round" style="--x:28%;--y:-12%;--p:.31"></span>
    <span class="shape ttb" style="--x:68%;--y:-7%;--p:.58"></span>
    <span class="shape btt" style="--x:20%;--y:104%;--p:.22"></span>
    <span class="shape btt tri" style="--x:44%;--y:106%;--p:.87"></span>
    <span class="shape btt round" style="--x:64%;--y:102%;--p:.49"></span>
    <span class="shape btt" style="--x:84%;--y:105%;--p:.15"></span>
    <span class="shape btt" style="--x:32%;--y:108%;--p:.70"></span>
    <span class="shape btt round" style="--x:74%;--y:103%;--p:.34"></span>
  </div>
  <main>
    <h1>PowerDNS API Proxy</h1>
    <div class="actions">
      <a href="/docs">Swagger Docs</a>
      <a href="https://github.com/akquinet/powerdns-api-proxy">GitHub</a>
    </div>
    <blockquote>
      The Domain Name Server (DNS) is the Achilles heel of the Web. The
      important thing is that it is managed responsibly.
    </blockquote>
    <p class="attribution">- Tim Berners-Lee</p>
  </main>
</body>
</html>
"""

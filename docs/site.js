// Website motion: sticky header, menus, mobile sheet, scroll progress,
// active section underline and scroll reveal. Works without it, too.
(() => {
  const root = document.documentElement;
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const bar = document.querySelector(".bar");
  const progress = document.querySelector(".progress");
  if (!bar) return;

  const onScroll = () => {
    const max = root.scrollHeight - innerHeight;
    progress?.style.setProperty("--p", max > 0 ? scrollY / max : 0);
    bar.classList.toggle("scrolled", scrollY > 8);
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Hover pill that glides between top-level items.
  const nav = bar.querySelector("nav.links");
  const pill = nav?.querySelector(".pill");
  const moveTo = (el) => {
    if (!pill) return;
    if (!el) { pill.style.opacity = "0"; return; }
    const r = el.getBoundingClientRect();
    pill.style.width = r.width + "px";
    pill.style.transform = `translateX(${r.left - nav.getBoundingClientRect().left}px)`;
    pill.style.opacity = "1";
  };
  const menus = [...bar.querySelectorAll(".mm")];
  let timer;
  const closeAll = (except) => menus.forEach((m) => {
    if (m === except) return;
    m.classList.remove("open");
    m.querySelector(".mt").setAttribute("aria-expanded", "false");
  });
  const open = (m) => {
    clearTimeout(timer);
    closeAll(m);
    m.classList.add("open");
    m.querySelector(".mt").setAttribute("aria-expanded", "true");
  };
  nav?.querySelectorAll(".mt").forEach((t) => t.addEventListener("mouseenter", () => moveTo(t)));
  nav?.addEventListener("mouseleave", () => {
    const o = menus.find((m) => m.classList.contains("open"));
    moveTo(o ? o.querySelector(".mt") : null);
  });
  menus.forEach((m) => {
    const t = m.querySelector(".mt");
    m.addEventListener("mouseenter", () => { if (matchMedia("(hover: hover)").matches) open(m); });
    m.addEventListener("mouseleave", () => {
      timer = setTimeout(() => { closeAll(); moveTo(null); }, 160);
    });
    t.addEventListener("click", () => {
      if (m.classList.contains("open")) { closeAll(); moveTo(null); } else { open(m); moveTo(t); }
    });
    m.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeAll(); moveTo(null); t.focus(); }
      if (e.key === "ArrowDown" && !m.classList.contains("open")) { e.preventDefault(); open(m); moveTo(t); m.querySelector(".mi")?.focus(); }
    });
    m.addEventListener("focusout", (e) => { if (!m.contains(e.relatedTarget)) { m.classList.remove("open"); t.setAttribute("aria-expanded", "false"); } });
  });
  document.addEventListener("click", (e) => { if (!bar.contains(e.target)) { closeAll(); moveTo(null); } });

  // Phone menu.
  const burger = bar.querySelector(".burger");
  const setSheet = (on) => {
    bar.classList.toggle("menu-open", on);
    document.body.classList.toggle("lock", on);
    burger?.setAttribute("aria-expanded", String(on));
  };
  burger?.addEventListener("click", () => setSheet(!bar.classList.contains("menu-open")));
  bar.querySelectorAll(".sheet a").forEach((a) => a.addEventListener("click", () => setSheet(false)));
  addEventListener("keydown", (e) => { if (e.key === "Escape") setSheet(false); });

  // Underline that follows the section in view.
  const jump = document.querySelector(".jump .wrap");
  if (jump) {
    const ink = document.createElement("span");
    ink.className = "jump-ink";
    jump.appendChild(ink);
    const links = [...jump.querySelectorAll("a")];
    const mark = (a) => {
      links.forEach((l) => l.classList.toggle("active", l === a));
      ink.style.width = a ? a.offsetWidth + "px" : "0";
      if (a) ink.style.transform = `translateX(${a.offsetLeft}px)`;
    };
    const targets = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
    const spy = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) mark(links.find((a) => a.getAttribute("href") === "#" + en.target.id));
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    targets.forEach((t) => spy.observe(t));
  }

  if (calm) return;
  root.classList.add("js");
  const groups = [".hero-text > *", ".hero-art", "section h2", "section p.sub", ".fcard", ".more",
    ".dl-card", ".steps", ".plan", ".gallery figure", "#faq details", "article > *", "a.card"];
  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
  }), { rootMargin: "0px 0px -8% 0px" });
  groups.forEach((sel) => document.querySelectorAll(sel).forEach((el, i) => {
    el.classList.add("reveal");
    el.style.setProperty("--d", String(Math.min(i, 6)));
    io.observe(el);
  }));

  // A gentle tilt on the hero screenshot.
  const art = document.querySelector(".hero-art img");
  if (art && matchMedia("(hover: hover)").matches) {
    const hero = document.querySelector(".hero-ms");
    hero.addEventListener("mousemove", (e) => {
      const r = hero.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      art.style.transform = `perspective(1600px) rotateY(${-6 + x * 6}deg) rotateX(${-y * 4}deg)`;
    });
    hero.addEventListener("mouseleave", () => { art.style.transform = ""; });
  }
})();

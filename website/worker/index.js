// User-requested takedown: every route is permanently gone.
export default {
  fetch() {
    return new Response('Gone\n', {status: 410, headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Robots-Tag': 'noindex, nofollow, noarchive'
    }});
  }
};

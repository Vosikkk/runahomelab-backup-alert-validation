## Want the alert without setting all of this up first?

I'm testing a tiny hosted backup alert for runahomelab.com.

The idea is intentionally small:

- your Proxmox/PBS backup fails;
- you get one Telegram message;
- no monitoring dashboard;
- no CPU graphs;
- no agent inside your lab.

Before I build the receiver, I'm testing whether people actually want this.

**[Send me a test backup alert](https://alerts.runahomelab.com/)**

The test does not connect to your Proxmox server. It only sends the same kind of Telegram message the finished version would send.

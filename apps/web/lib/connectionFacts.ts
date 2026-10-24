/**
 * Short, research-backed notes about conversation and connection, shown in the
 * Hot Seat lobby while people wait.
 *
 * Kept as a plain constant: it's static copy that changes with a deploy, so a
 * database table would add moving parts for nothing. The optional fields are
 * there so source links can be added later without reshaping anything.
 */
export interface ConnectionFact {
  id: string;
  title: string;
  body: string;
  source_label?: string;
  source_url?: string;
}

export const CONNECTION_FACTS: readonly ConnectionFact[] = [
  {
    id: "better-at-connecting",
    title: "We’re better at connecting than we think.",
    body: "People consistently underestimate how much others will enjoy talking with them.",
  },
  {
    id: "skip-small-talk",
    title: "Skip the small talk sometimes.",
    body: "Deeper conversations are usually less awkward—and more enjoyable—than people expect.",
  },
  {
    id: "curiosity",
    title: "Curiosity creates connection.",
    body: "People often underestimate how interested others are in hearing their honest answers.",
  },
  {
    id: "strangers-brighten-your-day",
    title: "Talking to strangers can brighten your day.",
    body: "Commuters who started conversations reported better experiences than those who stayed quiet.",
  },
  {
    id: "fast-reply",
    title: "A fast reply can feel like a real connection.",
    body: "Quick, natural responses during conversation are linked with stronger feelings of ‘clicking.’",
  },
  {
    id: "shared-laughter",
    title: "Shared laughter is social glue.",
    body: "People who laugh together tend to feel closer and more supported.",
  },
  {
    id: "variety",
    title: "Your social life benefits from variety.",
    body: "Interacting with different kinds of people—not only close friends—is associated with greater well-being.",
  },
  {
    id: "small-interactions",
    title: "Even small interactions count.",
    body: "Brief conversations with acquaintances and strangers can contribute to everyday happiness.",
  },
  {
    id: "relationships-and-health",
    title: "Good relationships are good for your health.",
    body: "Across 148 studies, stronger social relationships were associated with substantially better survival.",
  },
  {
    id: "quality-over-quantity",
    title: "Connection is more than having lots of friends.",
    body: "The quality, support, and closeness within relationships matter—not just the size of your network.",
  },
  {
    id: "longer-conversations",
    title: "Most people want the conversation to last longer.",
    body: "Research suggests conversations often end before either person actually wants them to.",
  },
  {
    id: "in-sync",
    title: "Enjoyable conversations can bring people into sync.",
    body: "After positive conversations, people’s views of themselves can become more aligned.",
  },
  {
    id: "people-care",
    title: "People may care more than you expect.",
    body: "We tend to underestimate how warmly others will respond when we share something personal.",
  },
  {
    id: "no-perfect-question",
    title: "Connection doesn’t require a perfect question.",
    body: "Simply giving someone your attention can make an interaction more rewarding.",
  },
  {
    id: "start-by-asking",
    title: "Knowing someone starts with asking.",
    body: "Meaningful questions can uncover similarities and stories that ordinary small talk misses.",
  },
];

/** How long each fact stays on screen. */
export const FACT_ROTATION_MS = 20_000;

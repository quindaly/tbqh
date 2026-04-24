"use client";

export default function Home() {
  return (
    <div className="text-center space-y-6 py-16">
      <h1 className="text-4xl font-bold">tbqh</h1>
      <p className="text-lg text-gray-600 dark:text-gray-400">
        Personalized discussion questions for your group.
      </p>
      <div className="flex gap-4 justify-center">
        <a
          href="/login"
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          Sign In
        </a>
        <a
          href="/join"
          className="px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
        >
          Join a Session
        </a>
      </div>
      <div className="pt-4">
        <a
          href="/games"
          className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition inline-block"
        >
          Play Social Games
        </a>
      </div>
    </div>
  );
}

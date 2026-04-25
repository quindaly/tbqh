"use client";

export default function Home() {
  return (
    <div className="text-center space-y-8 py-16">
      <h1 className="text-4xl font-bold">tbqh</h1>
      <p className="text-lg text-gray-600 dark:text-gray-400">
        Personalized discussion questions for your group.
      </p>

      <div className="flex flex-col gap-4 items-center pt-4">
        <a
          href="/games"
          className="w-72 px-6 py-4 bg-purple-600 text-white text-lg rounded-lg hover:bg-purple-700 transition inline-block"
        >
          Social Games
        </a>
        <a
          href="/questions"
          className="w-72 px-6 py-4 bg-blue-600 text-white text-lg rounded-lg hover:bg-blue-700 transition inline-block"
        >
          Discussion Questions
        </a>
      </div>

      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
          Want to save your favorites and build a profile?
        </p>
        <a
          href="/login"
          className="text-blue-600 hover:underline text-sm font-medium"
        >
          Sign in with email →
        </a>
      </div>
    </div>
  );
}

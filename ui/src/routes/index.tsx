import { createBrowserRouter, Navigate } from "react-router";
import Layout from "../app/dashboard";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";
import SyllabiPage from "@/app/plugins/syllabi";
import SyllabusDetailPage from "@/app/plugins/syllabi/detail";
import QuizPage from "@/app/plugins/syllabi/quiz";
import PublicSyllabusPage from "@/app/plugins/syllabi/public";
import GenerateContentPage from "@/app/plugins/generateContent";
import GenerateSyllabusPage from "@/app/plugins/generateSyllabus";
import EnrollPage from "@/app/plugins/enroll";
import AnalyticsPage from "@/app/plugins/analytics";
import LoginPage from "@/app/auth/login";
import SignupPage from "@/app/auth/signup";

const GlobalErrorBoundary = () => {
    return (
        <div className="flex min-h-[50vh] items-center justify-center p-4">
            <Card className="max-w-md shadow-lg">
                <CardHeader>
                    <CardTitle className="text-xl">Something went wrong</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-muted-foreground">
                        We're sorry, but we encountered an unexpected error.
                    </p>
                </CardContent>
                <CardFooter>
                    <Button asChild>
                        <a href="/">
                            <Home className="mr-2 h-4 w-4" />
                            Back to home
                        </a>
                    </Button>
                </CardFooter>
            </Card>
        </div>
    );
};

const router = createBrowserRouter([
    {
        path: "/login",
        element: <LoginPage />,
    },
    {
        path: "/signup",
        element: <SignupPage />,
    },
    {
        path: "/public/syllabi/:skillId",
        element: <PublicSyllabusPage />,
    },
    {
        path: "/",
        element: <Layout />,
        errorElement: <GlobalErrorBoundary />,
        children: [
            {
                index: true,
                element: <Navigate to="/analytics" replace />,
            },
            {
                path: "syllabi",
                element: <SyllabiPage />,
            },
            {
                path: "enroll",
                element: <EnrollPage />,
            },
            {
                path: "generate-syllabus",
                element: <GenerateSyllabusPage />,
            },
            {
                path: "generate-content",
                element: <GenerateContentPage />,
            },
            {
                path: "syllabi/:skillId",
                element: <SyllabusDetailPage />,
            },
            {
                path: "syllabi/:skillId/quiz",
                element: <QuizPage />,
            },
            {
                path: "analytics",
                element: <AnalyticsPage />,
            },
        ],
    },
]);

export default router;

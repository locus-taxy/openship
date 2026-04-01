import { createBrowserRouter } from "react-router";
import Layout from "../app/dashboard";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";
import SampleApp from "@/app/plugins/sampleApp";
import SyllabiPage from "@/app/plugins/syllabi";
import SyllabusDetailPage from "@/app/plugins/syllabi/detail";
import GenerateContentPage from "@/app/plugins/generateContent";
import GenerateSyllabusPage from "@/app/plugins/generateSyllabus";
import SubscribePage from "@/app/plugins/subscribe";
import useAuthStore from "@/store/authStore";
import useAuthDialogStore from "@/store/authDialogStore";
import { useEffect } from "react";

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
    const { isAuthenticated, initialized } = useAuthStore();
    const { openLogin } = useAuthDialogStore();

    useEffect(() => {
        if (initialized && !isAuthenticated) {
            openLogin();
        }
    }, [initialized, isAuthenticated]);

    if (!initialized) return null;

    if (!isAuthenticated) {
        return (
            <div className="flex items-center justify-center h-64 text-muted-foreground">
                Please sign in to access this page.
            </div>
        );
    }
    return <>{children}</>;
};

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
        path: "/",
        element: <Layout />,
        errorElement: <GlobalErrorBoundary />,
        children: [
            {
                path: "",
                element: <SampleApp />,
            },
            {
                path: "/sample-route",
                element: <SampleApp />,
            },
            {
                path: "/syllabi",
                element: (
                    <ProtectedRoute>
                        <SyllabiPage />
                    </ProtectedRoute>
                ),
            },
            {
                path: "/subscribe",
                element: (
                    <ProtectedRoute>
                        <SubscribePage />
                    </ProtectedRoute>
                ),
            },
            {
                path: "/generate-syllabus",
                element: (
                    <ProtectedRoute>
                        <GenerateSyllabusPage />
                    </ProtectedRoute>
                ),
            },
            {
                path: "/generate-content",
                element: (
                    <ProtectedRoute>
                        <GenerateContentPage />
                    </ProtectedRoute>
                ),
            },
            {
                path: "/syllabi/:skillId",
                element: (
                    <ProtectedRoute>
                        <SyllabusDetailPage />
                    </ProtectedRoute>
                ),
            },
        ],
    },
]);

export default router;

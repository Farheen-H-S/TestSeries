import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import MainLayout from '../components/layout/MainLayout';
import Home from '../pages/Home';
import Subjects from '../pages/Subjects';
import Upload from '../pages/Upload';
import Processing from '../pages/Processing';
import Review from '../pages/Review';
import QuestionBank from '../pages/QuestionBank';
import Generate from '../pages/Generate';
import PracticePaper from '../pages/PracticePaper';

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'subjects', element: <Subjects /> },
      { path: 'upload', element: <Upload /> },
      { path: 'processing/:documentId', element: <Processing /> },
      { path: 'review/:documentId', element: <Review /> },
      { path: 'question-bank', element: <QuestionBank /> },
      { path: 'generate', element: <Generate /> },
      { path: 'practice-paper/:paperId', element: <PracticePaper /> }
    ]
  }
]);

/**
 * Main application router utilizing React Router
 */
const AppRouter = () => {
  return <RouterProvider router={router} />;
};

export default AppRouter;

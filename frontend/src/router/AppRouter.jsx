import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainLayout from '../components/layout/MainLayout';
import Home from '../pages/Home';
import Upload from '../pages/Upload';
import Processing from '../pages/Processing';
import Review from '../pages/Review';
import QuestionBank from '../pages/QuestionBank';
import Generate from '../pages/Generate';
import PracticePaper from '../pages/PracticePaper';

/**
 * Main application router utilizing React Router
 */
const AppRouter = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Home />} />
          <Route path="upload" element={<Upload />} />
          <Route path="processing/:documentId" element={<Processing />} />
          <Route path="review/:documentId" element={<Review />} />
          <Route path="question-bank" element={<QuestionBank />} />
          <Route path="generate" element={<Generate />} />
          <Route path="practice-paper/:paperId" element={<PracticePaper />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
